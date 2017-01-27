from PyQt5.uic import loadUiType
from PyQt5 import QtGui
from PyQt5 import QtWidgets
from PyQt5.QtCore import QItemSelectionModel

from matplotlib.figure import Figure
# from matplotlib.backends.backend_qt4agg import (
#     FigureCanvasQTAgg as FigureCanvas,
#     NavigationToolbar2QT as NavigationToolbar)
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar)
from glob import glob
import re
import collections
import numpy as np

from model import (EncLog, EncoderLogTreeModel, OrderedDictModel,
                   VariableTreeModel)
from view import (EncLogTreeView, QRecursiveSelectionModel)


Ui_MainWindow, QMainWindow = loadUiType('mainWindow.ui')
Ui_PlotWidget, QWidget = loadUiType('plotWidget.ui')


class Main(QMainWindow, Ui_MainWindow):
    def __init__(self, ):
        super(Main, self).__init__()
        self.setupUi(self)
        self.fig_dict = {}

        self.plotAreaVerticalLayout = QtWidgets.QVBoxLayout()
        self.plotsFrame.setLayout(self.plotAreaVerticalLayout)

        # add a widget for previewing plots, they can then be added to the actual plot
        self.plotPreview = PlotWidget()
        self.plotAreaVerticalLayout.addWidget(self.plotPreview)

        # Create tree model to store encoder logs and connect it to view
        self.encoderLogTreeModel = EncoderLogTreeModel()
        self.encoderLogTreeView.setModel(self.encoderLogTreeModel)

        # Set custom selection model, so that sub items are automatically
        # selected if parent is selected
        self._selection_model = QRecursiveSelectionModel(self.encoderLogTreeView.model())
        self.encoderLogTreeView.setSelectionModel(self._selection_model)

        # Connect list view with model for the selected values of tree view
        self.selectedEncoderLogListModel = OrderedDictModel()
        self.encoderLogListView.setModel( self.selectedEncoderLogListModel )
        self._selection_model.selectionChanged.connect(self.change_list)

        # set up signals and slots
        self.selectedEncoderLogListModel.items_changed.connect(
            self.update_variable_tree
        )

        # Connect signals of menues
        self.actionOpen_File.triggered.connect(
            self.encoderLogTreeView.add_encoder_log
        )
        self.actionOpen_Sequence.triggered.connect(
            self.encoderLogTreeView.add_sequence
        )
        self.actionOpen_Directory.triggered.connect(
            self.encoderLogTreeView.add_folder
        )
        self.actionHide_PlotSettings.triggered.connect(
            self.setPlotSettingsVisibility
        )
        self.actionHide_Sequence.triggered.connect(
            self.setSequenceWidgetVisibility
        )

        self.variableTreeModel = VariableTreeModel()
        self.variableTreeView.setModel( self.variableTreeModel )
        self.plotsettings.visibilityChanged.connect(self.plotSettingsVisibilityChanged)
        self.sequenceWidget.visibilityChanged.connect(self.sequenceWidgetVisibilityChanged)

        # Set recursive selection model for variable view
        self._variable_tree_selection_model = QRecursiveSelectionModel(
            self.variableTreeView.model()
        )
        self.variableTreeView.setSelectionModel(
            self._variable_tree_selection_model
        )

        # sets Visibility for the Plotsettings Widget
    def setPlotSettingsVisibility(self):
        self.plotsettings.visibilityChanged.disconnect(self.plotSettingsVisibilityChanged)
        if self.plotsettings.isHidden():
            self.plotsettings.setVisible(True)
        else:
            self.plotsettings.setHidden(True)
        self.plotsettings.visibilityChanged.connect(self.plotSettingsVisibilityChanged)

    # updates the QAction if Visibility is changed
    def plotSettingsVisibilityChanged(self):
        if self.plotsettings.isHidden():
            self.actionHide_PlotSettings.setChecked(True)
        else:
            self.actionHide_PlotSettings.setChecked(False)

        #
        self._variable_tree_selection_model.selectionChanged.connect(
            self.update_plot
        )

        self.encoderLogTreeView.deleteKey.connect(self.remove)

    # sets Visibility for the Sequence Widget
    def setSequenceWidgetVisibility(self):
        self.sequenceWidget.visibilityChanged.disconnect(self.sequenceWidgetVisibilityChanged)
        if self.sequenceWidget.isHidden():
            self.sequenceWidget.setVisible(True)
        else:
            self.sequenceWidget.setHidden(True)
        self.sequenceWidget.visibilityChanged.connect(self.sequenceWidgetVisibilityChanged)

    def sequenceWidgetVisibilityChanged(self):
        if self.sequenceWidget.isHidden():
            self.actionHide_Sequence.setChecked(True)
        else:
            self.actionHide_Sequence.setChecked(False)

    # Sets Visibility for the Status Widget
    def setStatusWidgetVisibility(self):
        self.statusWidget.visibilityChanged.disconnect(self.statusWidgetVisibilityChanged)
        if self.statusWidget.isHidden():
            self.statusWidget.setVisible(True)
        else:
            self.statusWidget.setHidden(True)
        self.statusWidget.visibilityChanged.connect(self.statusWidgetVisibilityChanged)

    def remove(self):
        values = self.selectedEncoderLogListModel.values()
        #List call necessary to avoid runtime error because of elements changing
        #during iteration
        self.encoderLogTreeModel.remove( list( values ) )

    def change_list(self, q_selected, q_deselected):
        """Extend superclass behavior by automatically adding the values of
           all selected items in :param: `q_selected` to value list model. """

        selected_q_indexes = q_deselected.indexes()

        q_reselect_indexes = []
        for q_index in self.encoderLogTreeView.selectedIndexes():
            if q_index not in selected_q_indexes:
                q_reselect_indexes.append( q_index )

        # Find all all values that are contained by selected tree items
        tuples = []
        for q_index in q_selected.indexes() + q_reselect_indexes:
            # Add values, ie. encoder logs stored at the item, to the list
            # model.
            encoder_logs = q_index.internalPointer().values
            tuples.extend( (e.path, e) for e in encoder_logs )

        # Overwrite all elements in dictionary by selected values
        # Note, that ovrewriting only issues one `updated` signal, and thus,
        # only rerenders the plots one time. Therefore, simply overwriting
        # is much more efficient, despite it would seem, that selectively
        # overwriting keys is.
        self.selectedEncoderLogListModel.clear_and_update_from_tuples( tuples )

    def get_selected_enc_logs(self):
        return [self.selectedEncoderLogListModel[key] for key in self.selectedEncoderLogListModel]

    def get_plot_data_collection_from_selected_variables(self):
        """Get a :class: `dict` with y-variable as key and values as items
        from the current selection of the variable tree.

        :rtype: :class: `dict` of :class: `string` and :class: `list`
        """

        plot_data_collection = []
        for q_index in self.variableTreeView.selectedIndexes():
            item = q_index.internalPointer()
            if len( item.values ) > 0:
                plot_data_collection.extend( item.values )

        return plot_data_collection

    def update_variable_tree(self):
        """Collect all encoder logs currently selected, and create variable
        tree and corresponding data from it. Additionaly reselect all prevously
        selected variables.
        """

        # Create a list of all currently selected paths
        # Note, that *q_index* can not be used directly, because it might
        # change if the variable tree is recreated
        selected_path_collection = []
        for q_index in self.variableTreeView.selectedIndexes():
            selected_path_collection.append(
                # Create list of identifiers from path
                # Note, that the root node is excluded from the path
                [item.identifier for item in q_index.internalPointer().path[1:]]
            )

        # Join the data of all currently selected encoder logs to a dictionary
        # tree
        enc_logs = self.get_selected_enc_logs()
        dict_tree = EncLog.dict_tree_from_enc_logs(enc_logs)
        # Reset variable tree and update it with *dict_tree*
        self.variableTreeModel.clear_and_update_from_dict_tree( dict_tree )

        # Auto expand variable tree
        self.variableTreeView.expandAll()

        # Reselect all variables, which also exist on the new tree
        for path in selected_path_collection:
            # Try to reselect, and do nothing, if path does not exist anymore
            try:
                # Reselect new item corresponding to the previously selected
                # path
                item = self.variableTreeModel.get_item_from_path( *path )
                self.variableTreeView.selectionModel().select(
                    self.variableTreeModel._get_index_from_item( item ),
                    QItemSelectionModel.Select,
                )
            except KeyError:
                pass

    # updates the plot if the plot variable is changed
    def update_plot(self):
        plot_data_collection = self.get_plot_data_collection_from_selected_variables()

        self.plotPreview.change_plot( plot_data_collection )

    def clearPlot(self):
        pass



class NestedDict(dict):
    """
    Provides the nested dict used to store all the sequence data.
    """

    def __getitem__(self, key):
        if key in self: return self.get(key)
        return self.setdefault(key, NestedDict())


class PlotWidget(QWidget, Ui_PlotWidget):
    def __init__(self, ):
        super(PlotWidget, self).__init__()
        self.setupUi(self)
        self.fig_dict = {}

        self.fig = Figure()
        self.addmpl()

    # refreshes the figure according to new changes done
    def change_plot(self, plot_data_collection):
        """Plot all data from the *plot_data_collection*

        :param plot_data_collection: A iterable collection of :clas: `PlotData`
            objects, which should be plotted.
            temporal data
        """

        if len( plot_data_collection ) == 0:
            return

        # put a subplot into the figure and set the margins a little bit tighter than the defaults
        # this is some workaround for PyQt similar to tight layout
        self.fig.clear()
        axis = self.fig.add_subplot(111)
        self.fig.subplots_adjust(left=0.05, right=0.95,
                            bottom=0.1, top=0.95,
                            hspace=0.2, wspace=0.2)



        for plot_data in plot_data_collection:
            # Convert list of pairs of strings to two sorted lists of floats
            values = ( (float(x), float(y)) for (x, y) in plot_data.values)
            sorted_value_pairs = sorted(values, key=lambda pair: pair[0])
            [xs, ys] = list( zip(*sorted_value_pairs) )

            # Create legend from variable path and encoder log identifiers
            legend = " ".join(plot_data.identifiers + plot_data.path)

            axis.plot( xs, ys, label=legend )

        # distinguish between summary plot and temporal plot
        # if plotTypeSummary:
        #     axis.set_title('Summary Data')
        #     axis.set_xlabel('Bitrate [kbps]') #TODO is that k bytes or bits? need to check
        #     axis.set_ylabel( + ' [dB]')
        # else:
        #     axis.set_title('Temporal Data')
        #     axis.set_xlabel('POC')
        #     axis.set_ylabel(variable + ' [dB]')
        self.canvas.draw()

    # TODO Remove this? It will not work with the tree widget
    # def addfig(self, name, fig):
    #     self.fig_dict[name] = fig
    #     self.encoderLogTreeView.addItem(name)

    # adds a figure to the plotwidget
    def addmpl(self):
        # set backgroung to transparent
        self.fig.patch.set_alpha(0)
        # set some properties for canvas and add it to the vertical layout.
        # Most important is to turn the vertical stretch on as otherwise the plot is only scaled in x direction when rescaling the window
        self.canvas = FigureCanvas(self.fig)
        self.canvas.setParent(self.plotAreaWidget)
        policy = self.canvas.sizePolicy()
        policy.setVerticalStretch(1)
        self.canvas.setSizePolicy(policy)
        self.verticalLayout.addWidget(self.canvas)
        # add the toolbar for the plot
        self.toolbar = NavigationToolbar(self.canvas,
                                         self.plotAreaWidget, coordinates=True)
        self.verticalLayout.addWidget(self.toolbar)
        pass

    # removes a figure from the plotwidget
    def rmmpl(self, ):
        self.verticalLayout.removeWidget(self.canvas)
        self.canvas.close()
        self.verticalLayout.removeWidget(self.toolbar)
        self.toolbar.close()


class Graph():
    """"
    Hold all information on a single plot of a sequence.
    """

    def __init__(self):
        self.rd_points = {}


if __name__ == '__main__':
    import sys
    from PyQt5 import QtGui
    from PyQt5 import QtWidgets

    app = QtWidgets.QApplication(sys.argv)
    main = Main()
    main.show()
    sys.exit(app.exec_())
