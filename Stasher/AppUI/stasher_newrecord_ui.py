# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'stasher_newrecord.ui'
##
## Created by: Qt User Interface Compiler version 6.6.3
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QAbstractButton, QApplication, QDialog, QDialogButtonBox,
    QFrame, QGroupBox, QHeaderView, QLabel,
    QLineEdit, QPushButton, QSizePolicy, QTreeWidget,
    QTreeWidgetItem, QWidget)

class Ui_NewRecord(object):
    def setupUi(self, NewRecord):
        if not NewRecord.objectName():
            NewRecord.setObjectName(u"NewRecord")
        NewRecord.resize(801, 568)
        self.buttonBox = QDialogButtonBox(NewRecord)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setGeometry(QRect(440, 530, 341, 32))
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)
        self.Group_View = QGroupBox(NewRecord)
        self.Group_View.setObjectName(u"Group_View")
        self.Group_View.setGeometry(QRect(10, 200, 771, 321))
        self.View_AllRecordsTable = QTreeWidget(self.Group_View)
        QTreeWidgetItem(self.View_AllRecordsTable)
        self.View_AllRecordsTable.setObjectName(u"View_AllRecordsTable")
        self.View_AllRecordsTable.setGeometry(QRect(20, 30, 731, 281))
        self.Group_NewRecord = QGroupBox(NewRecord)
        self.Group_NewRecord.setObjectName(u"Group_NewRecord")
        self.Group_NewRecord.setGeometry(QRect(10, 0, 771, 191))
        self.NewRecord_UserInput = QLabel(self.Group_NewRecord)
        self.NewRecord_UserInput.setObjectName(u"NewRecord_UserInput")
        self.NewRecord_UserInput.setGeometry(QRect(10, 30, 81, 16))
        self.NewRecord_YourPath_Value = QLineEdit(self.Group_NewRecord)
        self.NewRecord_YourPath_Value.setObjectName(u"NewRecord_YourPath_Value")
        self.NewRecord_YourPath_Value.setGeometry(QRect(100, 30, 651, 21))
        self.NewRecord_Button_SetAsRootPath = QPushButton(self.Group_NewRecord)
        self.NewRecord_Button_SetAsRootPath.setObjectName(u"NewRecord_Button_SetAsRootPath")
        self.NewRecord_Button_SetAsRootPath.setGeometry(QRect(510, 60, 111, 26))
        self.NewRecord_Button_AddFileOrFolder = QPushButton(self.Group_NewRecord)
        self.NewRecord_Button_AddFileOrFolder.setObjectName(u"NewRecord_Button_AddFileOrFolder")
        self.NewRecord_Button_AddFileOrFolder.setGeometry(QRect(640, 60, 111, 26))
        self.NewRecord_Button_Undo = QPushButton(self.Group_NewRecord)
        self.NewRecord_Button_Undo.setObjectName(u"NewRecord_Button_Undo")
        self.NewRecord_Button_Undo.setGeometry(QRect(140, 60, 111, 26))
        self.NewRecord_Label_RecentlyStatus = QLabel(self.Group_NewRecord)
        self.NewRecord_Label_RecentlyStatus.setObjectName(u"NewRecord_Label_RecentlyStatus")
        self.NewRecord_Label_RecentlyStatus.setGeometry(QRect(10, 90, 741, 81))
        self.NewRecord_Label_RecentlyStatus.setFrameShape(QFrame.Box)
        self.NewRecord_Button_SetDesc = QPushButton(self.Group_NewRecord)
        self.NewRecord_Button_SetDesc.setObjectName(u"NewRecord_Button_SetDesc")
        self.NewRecord_Button_SetDesc.setGeometry(QRect(380, 60, 111, 26))
        self.NewRecord_Button_SetName = QPushButton(self.Group_NewRecord)
        self.NewRecord_Button_SetName.setObjectName(u"NewRecord_Button_SetName")
        self.NewRecord_Button_SetName.setGeometry(QRect(260, 60, 111, 26))

        self.retranslateUi(NewRecord)
        self.buttonBox.accepted.connect(NewRecord.accept)
        self.buttonBox.rejected.connect(NewRecord.reject)

        QMetaObject.connectSlotsByName(NewRecord)
    # setupUi

    def retranslateUi(self, NewRecord):
        NewRecord.setWindowTitle(QCoreApplication.translate("NewRecord", u"New record", None))
        self.Group_View.setTitle(QCoreApplication.translate("NewRecord", u"View", None))
        ___qtreewidgetitem = self.View_AllRecordsTable.headerItem()
        ___qtreewidgetitem.setText(3, QCoreApplication.translate("NewRecord", u"Path", None));
        ___qtreewidgetitem.setText(2, QCoreApplication.translate("NewRecord", u"Type", None));
        ___qtreewidgetitem.setText(1, QCoreApplication.translate("NewRecord", u"Name", None));
        ___qtreewidgetitem.setText(0, QCoreApplication.translate("NewRecord", u"No.", None));

        __sortingEnabled = self.View_AllRecordsTable.isSortingEnabled()
        self.View_AllRecordsTable.setSortingEnabled(False)
        ___qtreewidgetitem1 = self.View_AllRecordsTable.topLevelItem(0)
        ___qtreewidgetitem1.setText(3, QCoreApplication.translate("NewRecord", u"Path/to/file/or/folder", None));
        ___qtreewidgetitem1.setText(2, QCoreApplication.translate("NewRecord", u"Rootpath/File/Folder", None));
        ___qtreewidgetitem1.setText(1, QCoreApplication.translate("NewRecord", u"Filename/Foldername", None));
        ___qtreewidgetitem1.setText(0, QCoreApplication.translate("NewRecord", u"1", None));
        self.View_AllRecordsTable.setSortingEnabled(__sortingEnabled)

        self.Group_NewRecord.setTitle(QCoreApplication.translate("NewRecord", u"New record", None))
        self.NewRecord_UserInput.setText(QCoreApplication.translate("NewRecord", u"User input:", None))
        self.NewRecord_Button_SetAsRootPath.setText(QCoreApplication.translate("NewRecord", u"Set as root path", None))
        self.NewRecord_Button_AddFileOrFolder.setText(QCoreApplication.translate("NewRecord", u"Add file/folder", None))
        self.NewRecord_Button_Undo.setText(QCoreApplication.translate("NewRecord", u"Undo", None))
        self.NewRecord_Label_RecentlyStatus.setText(QCoreApplication.translate("NewRecord", u"Status", None))
        self.NewRecord_Button_SetDesc.setText(QCoreApplication.translate("NewRecord", u"Set as desc", None))
        self.NewRecord_Button_SetName.setText(QCoreApplication.translate("NewRecord", u"Set as name", None))
    # retranslateUi

