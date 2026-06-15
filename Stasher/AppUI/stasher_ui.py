# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'stasher.ui'
##
## Created by: Qt User Interface Compiler version 6.6.3
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QAction, QBrush, QColor, QConicalGradient,
    QCursor, QFont, QFontDatabase, QGradient,
    QIcon, QImage, QKeySequence, QLinearGradient,
    QPainter, QPalette, QPixmap, QRadialGradient,
    QTransform)
from PySide6.QtWidgets import (QApplication, QGroupBox, QHeaderView, QLabel,
    QLineEdit, QMainWindow, QMenu, QMenuBar,
    QPushButton, QSizePolicy, QStatusBar, QTreeWidget,
    QTreeWidgetItem, QWidget)

class Ui_StasherMain(object):
    def setupUi(self, StasherMain):
        if not StasherMain.objectName():
            StasherMain.setObjectName(u"StasherMain")
        StasherMain.resize(802, 667)
        self.actionOpen_config = QAction(StasherMain)
        self.actionOpen_config.setObjectName(u"actionOpen_config")
        self.actionClose = QAction(StasherMain)
        self.actionClose.setObjectName(u"actionClose")
        self.centralwidget = QWidget(StasherMain)
        self.centralwidget.setObjectName(u"centralwidget")
        self.Group_Summary = QGroupBox(self.centralwidget)
        self.Group_Summary.setObjectName(u"Group_Summary")
        self.Group_Summary.setGeometry(QRect(10, 0, 771, 111))
        self.Summary_NumberOfRecords = QLabel(self.Group_Summary)
        self.Summary_NumberOfRecords.setObjectName(u"Summary_NumberOfRecords")
        self.Summary_NumberOfRecords.setGeometry(QRect(20, 20, 121, 16))
        self.Summary_NumberOfRecords_Value = QLabel(self.Group_Summary)
        self.Summary_NumberOfRecords_Value.setObjectName(u"Summary_NumberOfRecords_Value")
        self.Summary_NumberOfRecords_Value.setGeometry(QRect(140, 20, 81, 16))
        self.Summary_Path2AppConfig = QLabel(self.Group_Summary)
        self.Summary_Path2AppConfig.setObjectName(u"Summary_Path2AppConfig")
        self.Summary_Path2AppConfig.setGeometry(QRect(20, 50, 121, 16))
        self.Summary_Path2AppConfig_Value = QLineEdit(self.Group_Summary)
        self.Summary_Path2AppConfig_Value.setObjectName(u"Summary_Path2AppConfig_Value")
        self.Summary_Path2AppConfig_Value.setGeometry(QRect(140, 50, 611, 21))
        self.Summary_Path2AppFolder = QLabel(self.Group_Summary)
        self.Summary_Path2AppFolder.setObjectName(u"Summary_Path2AppFolder")
        self.Summary_Path2AppFolder.setGeometry(QRect(20, 80, 121, 16))
        self.Summary_Path2AppFolder_Value = QLineEdit(self.Group_Summary)
        self.Summary_Path2AppFolder_Value.setObjectName(u"Summary_Path2AppFolder_Value")
        self.Summary_Path2AppFolder_Value.setGeometry(QRect(140, 80, 611, 21))
        self.Group_Edit = QGroupBox(self.centralwidget)
        self.Group_Edit.setObjectName(u"Group_Edit")
        self.Group_Edit.setGeometry(QRect(10, 120, 771, 101))
        self.Edit_Button_ListAllRecord = QPushButton(self.Group_Edit)
        self.Edit_Button_ListAllRecord.setObjectName(u"Edit_Button_ListAllRecord")
        self.Edit_Button_ListAllRecord.setGeometry(QRect(20, 20, 131, 26))
        self.Edit_Button_NewRecord = QPushButton(self.Group_Edit)
        self.Edit_Button_NewRecord.setObjectName(u"Edit_Button_NewRecord")
        self.Edit_Button_NewRecord.setGeometry(QRect(170, 20, 131, 26))
        self.Edit_GeneralUserInput = QLineEdit(self.Group_Edit)
        self.Edit_GeneralUserInput.setObjectName(u"Edit_GeneralUserInput")
        self.Edit_GeneralUserInput.setGeometry(QRect(20, 60, 731, 21))
        self.Edit_Button_SearchByName = QPushButton(self.Group_Edit)
        self.Edit_Button_SearchByName.setObjectName(u"Edit_Button_SearchByName")
        self.Edit_Button_SearchByName.setGeometry(QRect(320, 20, 131, 26))
        self.Edit_Button_SearchByNameDesc = QPushButton(self.Group_Edit)
        self.Edit_Button_SearchByNameDesc.setObjectName(u"Edit_Button_SearchByNameDesc")
        self.Edit_Button_SearchByNameDesc.setGeometry(QRect(470, 20, 131, 26))
        self.Edit_Button_RefreshRecords = QPushButton(self.Group_Edit)
        self.Edit_Button_RefreshRecords.setObjectName(u"Edit_Button_RefreshRecords")
        self.Edit_Button_RefreshRecords.setGeometry(QRect(620, 20, 131, 26))
        self.Group_View = QGroupBox(self.centralwidget)
        self.Group_View.setObjectName(u"Group_View")
        self.Group_View.setGeometry(QRect(10, 230, 771, 371))
        self.View_AllRecordsTable = QTreeWidget(self.Group_View)
        QTreeWidgetItem(self.View_AllRecordsTable)
        self.View_AllRecordsTable.setObjectName(u"View_AllRecordsTable")
        self.View_AllRecordsTable.setGeometry(QRect(20, 30, 731, 291))
        self.View_Path2PatchFolder_Button = QPushButton(self.Group_View)
        self.View_Path2PatchFolder_Button.setObjectName(u"View_Path2PatchFolder_Button")
        self.View_Path2PatchFolder_Button.setGeometry(QRect(670, 330, 81, 31))
        self.View_Path2PatchFolder_Value = QLineEdit(self.Group_View)
        self.View_Path2PatchFolder_Value.setObjectName(u"View_Path2PatchFolder_Value")
        self.View_Path2PatchFolder_Value.setGeometry(QRect(20, 330, 641, 31))
        StasherMain.setCentralWidget(self.centralwidget)
        self.menubar = QMenuBar(StasherMain)
        self.menubar.setObjectName(u"menubar")
        self.menubar.setGeometry(QRect(0, 0, 802, 23))
        self.menuFile = QMenu(self.menubar)
        self.menuFile.setObjectName(u"menuFile")
        StasherMain.setMenuBar(self.menubar)
        self.statusbar = QStatusBar(StasherMain)
        self.statusbar.setObjectName(u"statusbar")
        StasherMain.setStatusBar(self.statusbar)

        self.menubar.addAction(self.menuFile.menuAction())
        self.menuFile.addAction(self.actionOpen_config)
        self.menuFile.addAction(self.actionClose)

        self.retranslateUi(StasherMain)

        QMetaObject.connectSlotsByName(StasherMain)
    # setupUi

    def retranslateUi(self, StasherMain):
        StasherMain.setWindowTitle(QCoreApplication.translate("StasherMain", u"Stasher Main Window", None))
        self.actionOpen_config.setText(QCoreApplication.translate("StasherMain", u"Open config", None))
        self.actionClose.setText(QCoreApplication.translate("StasherMain", u"Close", None))
        self.Group_Summary.setTitle(QCoreApplication.translate("StasherMain", u"Summary", None))
        self.Summary_NumberOfRecords.setText(QCoreApplication.translate("StasherMain", u"Number of record(s):", None))
        self.Summary_NumberOfRecords_Value.setText(QCoreApplication.translate("StasherMain", u"0", None))
        self.Summary_Path2AppConfig.setText(QCoreApplication.translate("StasherMain", u"Config's path:", None))
        self.Summary_Path2AppFolder.setText(QCoreApplication.translate("StasherMain", u"App's folder path:", None))
        self.Group_Edit.setTitle(QCoreApplication.translate("StasherMain", u"Edit", None))
        self.Edit_Button_ListAllRecord.setText(QCoreApplication.translate("StasherMain", u"List all record(s)", None))
        self.Edit_Button_NewRecord.setText(QCoreApplication.translate("StasherMain", u"New record", None))
        self.Edit_Button_SearchByName.setText(QCoreApplication.translate("StasherMain", u"Search by Name", None))
        self.Edit_Button_SearchByNameDesc.setText(QCoreApplication.translate("StasherMain", u"Search by Desc", None))
        self.Edit_Button_RefreshRecords.setText(QCoreApplication.translate("StasherMain", u"Refresh record(s)", None))
        self.Group_View.setTitle(QCoreApplication.translate("StasherMain", u"View", None))
        ___qtreewidgetitem = self.View_AllRecordsTable.headerItem()
        ___qtreewidgetitem.setText(4, QCoreApplication.translate("StasherMain", u"Desc", None));
        ___qtreewidgetitem.setText(3, QCoreApplication.translate("StasherMain", u"File(s)/Folder(s)", None));
        ___qtreewidgetitem.setText(2, QCoreApplication.translate("StasherMain", u"RootDir", None));
        ___qtreewidgetitem.setText(1, QCoreApplication.translate("StasherMain", u"Name", None));
        ___qtreewidgetitem.setText(0, QCoreApplication.translate("StasherMain", u"No.", None));

        __sortingEnabled = self.View_AllRecordsTable.isSortingEnabled()
        self.View_AllRecordsTable.setSortingEnabled(False)
        ___qtreewidgetitem1 = self.View_AllRecordsTable.topLevelItem(0)
        ___qtreewidgetitem1.setText(4, QCoreApplication.translate("StasherMain", u"Record Desc 0", None));
        ___qtreewidgetitem1.setText(3, QCoreApplication.translate("StasherMain", u"file0 <br> file1 <br> file2 ", None));
        ___qtreewidgetitem1.setText(2, QCoreApplication.translate("StasherMain", u"/path/to/rootdir", None));
        ___qtreewidgetitem1.setText(1, QCoreApplication.translate("StasherMain", u"Record Name 0", None));
        ___qtreewidgetitem1.setText(0, QCoreApplication.translate("StasherMain", u"1", None));
        self.View_AllRecordsTable.setSortingEnabled(__sortingEnabled)

        self.View_Path2PatchFolder_Button.setText(QCoreApplication.translate("StasherMain", u"Paste into", None))
        self.menuFile.setTitle(QCoreApplication.translate("StasherMain", u"File", None))
    # retranslateUi

