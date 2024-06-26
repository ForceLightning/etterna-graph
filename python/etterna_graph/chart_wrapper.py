from datetime import datetime
import math
from typing import *

import pyqtgraph as pg
from pyqtgraph.graphicsItems.PlotItem import PlotItem

from . import app
from . import util


"""
This file handles all graphics library interaction through the classes
PlotFrame, Plot and TextBox (and the internal utility classes
TimeAxisItem and DIYLogAxisItem)
"""


class TimeAxisItem(pg.AxisItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setLabel(units=None)
        self.enableAutoSIPrefix(False)

    def tickStrings(self, values, _scale, _spacing):
        # Cap timestamp to 32 bit to prevent crash on Windows from
        # out-of-bounds dates
        capmin = 0
        capmax = (2**31) - 1

        strings = []
        for value in values:
            value = min(capmax, max(capmin, value))
            strings.append(datetime.fromtimestamp(value).strftime("%Y-%m-%d"))
        return strings


class DIYLogAxisItem(pg.AxisItem):
    def __init__(
        self,
        accuracy,
        decimal_places,
        postfix="",
        max_shown_value=float("inf"),
        min_shown_value=float("-inf"),
        *args,
        **kwargs,
    ):

        super().__init__(*args, **kwargs)
        self.setLabel(units=None)
        self.enableAutoSIPrefix(False)

        self.accuracy = accuracy
        self.decimal_places = decimal_places
        self.postfix = postfix
        self.max_shown_value = max_shown_value
        self.min_shown_value = min_shown_value

    def tickStrings(self, values, _scale, _spacing):
        result = []
        for value in values:
            if self.accuracy:
                value = 100 - 10**-value
            else:
                value = 10**value

            if value > self.max_shown_value:
                string = (
                    str(round(self.max_shown_value, self.decimal_places))
                    + self.postfix
                    + "+"
                )
            elif value < self.min_shown_value:
                string = (
                    "less than "
                    + str(round(self.min_shown_value, self.decimal_places))
                    + self.postfix
                )
            else:
                string = str(round(value, self.decimal_places)) + self.postfix

            result.append(string)
        return result


# mapper: function that turns xml into data points
# color: chart color (duh)
# alpha: transparency of scatter points
# mapper_args: extra parameters passed to `mapper`
# legend: list of strings as the legend, for the stacked bar chart.
# click_callback: callback for when a scatter point is clicked. The
#  callback is called with the point data as parameter
# type_: either "scatter", "bubble", "bar", "stacked bar" or
#  "stacked line"
# width: (only for bar charts) width of the bars
def draw(
    data: tuple[Iterable, ...],
    flags: str = "",
    title: str | None = None,
    color: str | list[str] = "white",
    alpha: float = 0.4,
    legend: list[str] | None = None,
    log_axis_max_shown_value=None,
    log_axis_min_shown_value=None,
    click_callback: Callable | None = None,
    type_: str = "scatter",
    width: float = 0.8,
):

    log_axis_kwargs = {}
    if log_axis_max_shown_value:
        log_axis_kwargs["max_shown_value"] = log_axis_max_shown_value
    if log_axis_min_shown_value:
        log_axis_kwargs["min_shown_value"] = log_axis_min_shown_value

    axisItems = {}
    if "time_xaxis" in flags:
        axisItems["bottom"] = TimeAxisItem(orientation="bottom")
    if "accuracy_yaxis" in flags:
        axisItems["left"] = DIYLogAxisItem(
            accuracy=True,
            decimal_places=3,
            postfix="%",
            orientation="left",
            **log_axis_kwargs,
        )
    elif "manip_yaxis" in flags:
        axisItems["left"] = DIYLogAxisItem(
            accuracy=False,
            decimal_places=1,
            postfix="%",
            orientation="left",
            **log_axis_kwargs,
        )
    elif "ma_yaxis" in flags:
        axisItems["left"] = DIYLogAxisItem(
            accuracy=False, decimal_places=1, orientation="left", **log_axis_kwargs
        )

    plot_widget = pg.PlotWidget(axisItems=axisItems)
    plot: PlotItem = plot_widget.getPlotItem()
    plot.setTitle(title)
    if "log" in flags:
        plot.setLogMode(x=False, y=True)  # does this do anything? idk

    if "diagonal_line" in flags:
        plot.addItem(pg.InfiniteLine(pos=(0, 0), angle=45, pen="w"))

    def click_handler(_, points):
        if len(points) > 1:
            app.app.set_infobar(f"{len(points)} points selected at once!")
        elif click_callback is not None:
            try:
                (click_callback)(points[0].data())
            except Exception:
                util.logger.exception("Click handler")
                app.app.set_infobar("[Error while generating info text]")

    # ~ plot.clear()

    if isinstance(data, str):
        item = pg.TextItem(data, anchor=(0.5, 0.5))
        plot.addItem(item)
        return

    ids = None

    # We may have ids given which we need to separate
    if click_callback is not None:
        (data, ids) = data
    if type_ == "bubble":
        (x, y, sizes) = data
    else:
        (x, y) = data

    if "time_xaxis" in flags and x is not None:
        x = [value.timestamp() for value in x]

    step_mode = "step" in flags
    if step_mode and x is not None:
        x = [*x, x[-1]]  # Duplicate last element to satisfy pyqtgraph with stepMode
        # Out-of-place to avoid modifying the passed-in list

    if legend is not None:
        plot.addLegend()
        plot.legend.setBrush(app.app.prefs.legend_bg_color)
        plot.legend.setPen(util.border_color())

    if type_ == "stacked bar" and y is not None:
        num_cols = len(y)
        y = list(zip(*y))
        bottom = [0] * num_cols
        for row_i, row in enumerate(y):
            # item = pg.BarGraphItem(x=x, y0=bottom, height=row, width=1, pen=(0,0,0,255), brush=color[row_i])
            item = pg.BarGraphItem(
                x=x,
                y0=bottom,
                height=row,
                width=width,
                pen=color[row_i],
                brush=color[row_i],
            )
            bottom = [a + b for (a, b) in zip(bottom, row)]  # We need out-of-place here
            if legend is not None:
                plot.legend.addItem(item, legend[row_i])
            plot.addItem(item)
    elif type_ == "stacked line":
        num_cols = len(y)
        y = list(zip(*y))
        # Iterate in reverse so that overall comes last and draws
        # above the rest
        for row_i, row in reversed(list(enumerate(y))):
            # ~ item = pg.PlotCurveItem(x=x, y=list(row), pen=color[row_i], brush=color[row_i], stepMode=step_mode)
            width = 3 if row_i == 0 else 1
            pen = pg.mkPen(color[row_i], width=width)
            item = pg.PlotCurveItem(x=x, y=list(row), pen=pen, stepMode=step_mode)
            if legend is not None:
                plot.legend.addItem(item, legend[row_i])
            plot.addItem(item)
    else:
        if isinstance(color, list):
            for i in range(len(color)):
                color[i] = pg.mkColor(color[i])
                color[i].setAlphaF(alpha)
        else:
            color = pg.mkColor(color)
            color.setAlphaF(alpha)
        if type_ == "scatter":
            item = pg.ScatterPlotItem(x, y, pen=None, size=8, brush=color, data=ids)
        elif type_ == "bar":
            x_values = [v + 0.5 for v in x] if "align_to_whole" in flags else x
            item = pg.BarGraphItem(
                x=x_values, height=y, width=width, pen=(200, 200, 200), brush=color
            )
        elif type_ == "bubble":
            item = pg.ScatterPlotItem(x, y, pen=None, size=sizes, brush=color, data=ids)
        elif type_ == "line":
            width = 3 if "thick_line" in flags else 1
            item = pg.PlotDataItem(
                x, y, pen=pg.mkPen(color, width=width), stepMode=step_mode
            )

        if click_callback is not None:
            item.sigClicked.connect(click_handler)
        plot.addItem(item)

    # Add horizontal score threshold lines
    if "accuracy_yaxis" in flags:
        plot.addLine(y=-(math.log(100 - 60.00) / math.log(10)), pen="#c97bff")
        plot.addLine(y=-(math.log(100 - 70.00) / math.log(10)), pen="#5b78bb")
        plot.addLine(y=-(math.log(100 - 80.00) / math.log(10)), pen="#da5757")
        plot.addLine(y=-(math.log(100 - 93.00) / math.log(10)), pen="#66cc66")
        plot.addLine(y=-(math.log(100 - 99.75) / math.log(10)), pen="#eebb00")
        plot.addLine(y=-(math.log(100 - 99.97) / math.log(10)), pen="#66ccff")
        plot.addLine(y=-(math.log(100 - 99.999) / math.log(10)), pen="#ffffff")

    plot.autoBtnClicked()
    plot.showGrid(x=True, y=True, alpha=0.15)
    return plot_widget
