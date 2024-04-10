"""
Define the LinearRHSChecker class.

LinearRHSChecker manages caching of solutions and right-hand sides for linear solves.
"""

import os
from collections import deque
import atexit

import numpy as np

from math import isclose
from openmdao.utils.array_utils import allclose, allzero
from openmdao.utils.file_utils import text2html
from openmdao.utils.om_warnings import issue_warning
from openmdao.visualization.tables.table_builder import generate_table


_cache_stats = {}


def _print_stats():
    """
    Print out cache statistics at the end of the run.
    """
    if _cache_stats:
        headers = ['System', 'Eq Hits', 'Neg Hits', 'Parallel Hits', 'Zero Hits', 'Misses',
                   'Resets']
        for repors_dir, dct in _cache_stats.items():
            rows = []
            for syspath, stats in dct.items():
                rows.append([syspath, stats['eqhits'], stats['neghits'], stats['parhits'],
                             stats['zerohits'], stats['misses'], stats['resets']])

            table = generate_table(rows, tablefmt='html', headers=headers)

            if not os.path.exists(repors_dir):
                os.makedirs(repors_dir)

            with open(os.path.join(repors_dir, 'linear_rhs_cache_stats.html'), 'w') as f:
                print(str(table), file=f)


class LinearRHSChecker(object):
    """
    Class that manages caching of linear solutions.

    Parameters
    ----------
    system : System
        The system that owns the solver that owns this LinearRHSChecker.
    max_cache_entries : int
        Maximum number of solutions to cache.
    check_zero : bool
        If True, check if the RHS vector is zero.
    rtol : float
        Relative tolerance for equivalence checks.
    atol : float
        Absolute tolerance for equivalence checks.
    collect_stats : bool
        If True, collect cache statistics.

    Attributes
    ----------
    _caches : list
        List of cached solutions.
    _ncompute_totals : int
        Total number of compute_totals calls. Used to determine when to
        reset the cache.
    _check_zero : bool
        If True, check if the RHS vector is zero.
    _rtol : float
        Relative tolerance for equivalence check.
    _atol : float
        Absolute tolerance for equivalence check.
    _stats : dict or None
        Dictionary to store cache statistics.
    """

    options = ('use_cache', 'check_zero', 'rtol', 'atol', 'max_cache_entries', 'collect_stats',
               'auto')

    def __init__(self, system, max_cache_entries=3, check_zero=True, rtol=3e-16, atol=3e-16,
                 collect_stats=False):
        """
        Initialize the LinearRHSChecker.
        """
        global _cache_stats

        self._caches = deque(maxlen=max_cache_entries)
        self._ncompute_totals = system._problem_meta['ncompute_totals']
        self._check_zero = check_zero
        self._rtol = rtol
        self._atol = atol
        # print out cache stats at the end of the run
        if collect_stats:
            self._stats = {
                'eqhits': 0, 'neghits': 0, 'parhits': 0, 'zerohits': 0, 'misses': 0, 'resets': 0
            }
            reports_dir = system._problem_meta['reports_dir']
            if not _cache_stats:
                atexit.register(_print_stats)
            if reports_dir not in _cache_stats:
                _cache_stats[reports_dir] = {}
            _cache_stats[reports_dir][system.pathname] = self._stats
        else:
            self._stats = None

        # check if cache is necessary and warn if not
        if max_cache_entries > 0:
            if system.pathname not in system._relevance.get_redundant_adjoint_systems():
                issue_warning(f"{system.msginfo}: 'rhs_checking' is active but no redundant adjoint"
                              " dependencies were found, so caching is unlikely to be beneficial.")

    @staticmethod
    def check_options(system, options):
        """
        Check the options dictionary for the presence of LinearRHSChecker options.

        Parameters
        ----------
        system : System
            The system that owns the solver that owns this LinearRHSChecker.
        options : dict
            The options dictionary.

        Returns
        -------
        bool
            True if LinearRHSChecker options are present in the options dictionary.
        """
        invalid = set(options).difference(LinearRHSChecker.options)
        if invalid:
            raise ValueError(f"{system.msginfo}: unrecognized 'rhs_checking' options "
                             f"{sorted(invalid)}. Valid options are {LinearRHSChecker.options}.")

    def clear(self):
        """
        Clear the cache.
        """
        self._caches.clear()

    def add_solution(self, rhs, solution):
        """
        Add a solution to the cache.

        Parameters
        ----------
        rhs : ndarray
            The RHS vector.
        solution : ndarray
            The solution vector.
        """
        if self._caches.maxlen > 0:
            self._caches.append((rhs.copy(), solution.copy()))

    def get_solution(self, rhs_arr, system):
        """
        Return a cached solution if the RHS vector matches a cached vector.

        Also indicates if the RHS vector is zero.

        Parameters
        ----------
        rhs_arr : ndarray
            The RHS vector.
        system : System
            The system that owns the solver that owns this LinearRHSChecker.

        Returns
        -------
        ndarray or None
            The cached solution if the RHS vector matches a cached vector, or None if no match
            is found.
        bool
            True if the rhs array is zero.
        """
        if system.under_complex_step:
            return None, False

        if self._check_zero:
            if system.comm.size > 1:
                # check if the whole distributed array is zero
                if system.comm.allreduce(int(allzero(rhs_arr))) == system.comm.size:
                    if self._stats is not None:
                        self._stats['zerohits'] += 1
                    return None, True
            elif allzero(rhs_arr):
                if self._stats is not None:
                    self._stats['zerohits'] += 1
                return None, True

        if self._caches.maxlen == 0:
            return None, False

        sol_array = None

        if self._ncompute_totals != system._problem_meta['ncompute_totals']:
            # reset the cache if we've run compute_totals since the last time we used the cache
            self.clear()
            self._ncompute_totals = system._problem_meta['ncompute_totals']
            if self._stats is not None:
                self._stats['resets'] += 1

        for i in range(len(self._caches) - 1, -1, -1):
            rhs_cache, sol_cache = self._caches[i]
            # Check if the RHS vector is the same as a cached vector. This part is not necessary,
            # but is less expensive than checking if two vectors are parallel.
            if allclose(rhs_arr, rhs_cache, rtol=self._rtol, atol=self._atol):
                sol_array = sol_cache
                if self._stats is not None:
                    self._stats['eqhits'] += 1
                break

            # Check if the RHS vector is equal to -1 * cached vector.
            if allclose(rhs_arr, -rhs_cache, rtol=self._rtol, atol=self._atol):
                sol_array = -sol_cache
                if self._stats is not None:
                    self._stats['neghits'] += 1
                break

            # Check if the RHS vector and a cached vector are parallel
            dot_product = np.dot(rhs_arr, rhs_cache)
            rhs_norm = np.linalg.norm(rhs_arr)
            rhs_cache_norm = np.linalg.norm(rhs_cache)
            if isclose(abs(dot_product), rhs_norm * rhs_cache_norm,
                       rel_tol=self._rtol, abs_tol=self._atol):
                # two vectors are parallel, thus we can use the cache.
                if rhs_cache_norm > 0.0:
                    scaler = dot_product / rhs_cache_norm**2
                    sol_array = sol_cache * scaler
                    if self._stats is not None:
                        self._stats['parhits'] += 1
                    break

        matched_cache = int(sol_array is not None)

        if system.comm.size > 1:
            # only match if the entire distributed array matches the cache
            if system.comm.allreduce(matched_cache) != system.comm.size:
                matched_cache = 0

        if not matched_cache and self._stats is not None:
            self._stats['misses'] += 1

        return sol_array if matched_cache else None, False
