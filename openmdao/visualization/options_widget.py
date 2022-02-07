"""
A widget that lets users set options from the root group of a model,
after the model has been instantiated but before setup has been called.

Timing is important here. After model has been instantiated, but before setup(),
the options dict should exist. User could still change option values at this point though.

A widget that lets them interact with common options. Setting any float/int. Checkboxes for bools.
If there is a set of specific values, provide them in a drop down.

Some options may need to be tagged as non-GUI-able. Ones that take function pointers, classes, or
instances seem like things you couldn't do in the gui. So we may need to add tags to the options
(recordable seems like a tag already), or just another metadata field perhaps.

Its critical the user can set these values before setup, because often some of these options change
the way the model is configured. After setup, these options should not be allowed to change.
"""

try:
    import ipywidgets as widgets
    from ipywidgets import DOMWidget, register
    from ipywidgets import interact, Layout
    from IPython.display import display
except Exception:
    widgets = None

# from traitlets import Unicode, Bool, validate, TraitError


# @register
# class Email(DOMWidget):

from openmdao.utils.options_dictionary import OptionsDictionary
from openmdao.utils.general_utils import simple_warning

class OptionsWidget(object):
    """
    Widget to set options.

    Parameters
    ----------
    opts : OptionsDictionary
        options to edit.
    """

    def __init__(self, opts):
        """
        Initialize.
        """
        if widgets is None:
            simple_warning(f"ipywidgets is required to use {self.__class__.__name__}."
                           "To install it run `pip install openmdao[notebooks]`.")
            return

        _dict = opts._dict
        _widgets = {}
        _style = {'description_width': 'initial', 'align-items': 'center'}


        for name, option in _dict.items():
            print(f"{name} {option=}")
            print(f"----------------")

            val = option['val']
            values = option['values']
            desc = option['desc']

            if values:
                _widgets[name] = widgets.Dropdown(
                    description=name,
                    options=values,
                    value=val,
                    disabled=False,
                    layout=Layout(width='50%'),
                    style=_style
                )
                continue

            upper = option['upper']
            lower = option['lower']

            if upper and lower:
                if isinstance(val, int):
                    _widgets[name] = widgets.IntSlider(
                        description=name,
                        min=lower,
                        max=upper,
                        value=val,
                        step=1,
                        disabled=False,
                        continuous_update=False,
                        orientation='horizontal',
                        readout=True,
                        readout_format='d',
                        layout=Layout(width='50%'),
                        style=_style
                    )
                else:
                    _widgets[name] = widgets.FloatSlider(
                        description=name,
                        min=lower,
                        max=upper,
                        value=val,
                        disabled=False,
                        continuous_update=False,
                        orientation='horizontal',
                        readout=True,
                        readout_format='f',
                        layout=Layout(width='50%'),
                        style=_style
                    )
                continue

            if isinstance(val, float):
                _widgets[name] = widgets.FloatText(
                    description=name,
                    min=lower,
                    max=upper,
                    value=val,
                    disabled=False,
                    continuous_update=False,
                    orientation='horizontal',
                    readout=True,
                    readout_format='f',
                    layout=Layout(width='50%'),
                    style=_style
                )
                continue

            if isinstance(val, int):
                _widgets[name] = widgets.IntText(
                    description=name,
                    min=lower,
                    max=upper,
                    value=val,
                    step=1,
                    disabled=False,
                    continuous_update=False,
                    orientation='horizontal',
                    readout=True,
                    readout_format='d',
                    layout=Layout(width='50%'),
                    style=_style
                )
                continue

            types = option['types']

            if types == list:
                _widgets[name] = widgets.SelectMultiple(
                    description=name,
                    options=[],
                    rows=5,
                    disabled=False,
                    layout=Layout(width='50%'),
                    style=_style
                )
                continue

            print(f"----\nWidget not implemented for {name}: {option}\n----")

        for wdgt in _widgets.values():
            display(wdgt)

        # messages = widgets.Output()
        # @messages.capture(clear_output=True)
        # def display():
        #     for wdgt in _widgets.values():
        #         display(wdgt)

        # display()

        # @messages.capture(clear_output=True)
        # interact(plot_func, source=w_source, cases=w_cases, xaxis=w_xaxis, yaxis=w_yaxis,
        #             disabled=False)
        # display(messages)
