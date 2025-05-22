import os
import qt
import slicer
import subprocess
import sys
from slicer.ScriptedLoadableModule import *
from qt import QTreeView, QFileSystemModel, QPushButton, QFileDialog
import logging

class LungSegmentation(ScriptedLoadableModule):
    def __init__(self, parent):
        parent.title = "LungSegmentation"
        parent.categories = ["Segmentation"]
        parent.contributors = ["Florian Davaux (CREATIS)"]
        parent.helpText = "Segmentation automatique des structures pulmonaires"
        parent.acknowledgementText = "Projet KOLOR SPCCT"
        self.parent = parent

class LungSegmentationWidget(ScriptedLoadableModuleWidget):
    def setup(self):
        self.install_dependencies_if_needed()
        ScriptedLoadableModuleWidget.setup(self)

        uiWidget = slicer.util.loadUI(os.path.join(os.path.dirname(__file__), 'Resources', 'UI', 'LungSegmentation.ui'))
        self.layout.addWidget(uiWidget)
        self.layout.setContentsMargins(0, 0, 0, 0)


        # Récupération des widgets
        self.checkBoxInvivoParenchyma = uiWidget.findChild(qt.QCheckBox, "checkBoxInvivoParenchyma")
        self.checkBoxInvivoAirways = uiWidget.findChild(qt.QCheckBox, "checkBoxInvivoAirways")
        self.checkBoxInvivoVascularTree = uiWidget.findChild(qt.QCheckBox, "checkBoxInvivoVascularTree")

        self.checkBoxExvivoParenchyma = uiWidget.findChild(qt.QCheckBox, "checkBoxExvivoParenchyma")
        self.checkBoxExvivoAirways = uiWidget.findChild(qt.QCheckBox, "checkBoxExvivoAirways")


        self.browseInputButton = uiWidget.findChild(qt.QPushButton, "browseInputButton")
        self.lineEditInputPath = uiWidget.findChild(qt.QLineEdit, "inputLineEdit")

        self.browseOutputButton = uiWidget.findChild(qt.QPushButton, "browseOutputButton")
        self.lineEditOutputPath = uiWidget.findChild(qt.QLineEdit, "outputLineEdit")

        self.segmentationButton = uiWidget.findChild(qt.QPushButton, "pushButtonSegmentation")

        # Connexions
        for checkbox in [self.checkBoxInvivoParenchyma, self.checkBoxInvivoAirways, self.checkBoxInvivoVascularTree,
                 self.checkBoxExvivoParenchyma, self.checkBoxExvivoAirways]:
            checkbox.toggled.connect(lambda state, cb=checkbox: self.validateCheckboxes(cb))

        self.browseInputButton.clicked.connect(lambda: self.openDialog("input"))
        self.browseOutputButton.clicked.connect(lambda: self.openDialog("output"))
        self.segmentationButton.clicked.connect(self.onSegmentationButtonClicked)
    
    def install_dependencies_if_needed(self):
        try:
            import nnunetv2
            print("✅ nnU-Net v2 déjà installé.")
        except ImportError:
            install = qt.QMessageBox.question(
                slicer.util.mainWindow(),
                "nnU-Net non installé",
                "Le module nnU-Net v2 n'est pas installé. Voulez-vous l’installer maintenant ?",
                qt.QMessageBox.Yes | qt.QMessageBox.No
            )
            if install == qt.QMessageBox.Yes:
                try:
                    python_exec = sys.executable
                    subprocess.check_call([python_exec, "-m", "pip", "install", "nnunetv2"])
                    qt.QMessageBox.information(
                        slicer.util.mainWindow(), "Installation réussie", "nnU-Net v2 a été installé avec succès."
                    )
                except subprocess.CalledProcessError as e:
                    qt.QMessageBox.critical(
                        slicer.util.mainWindow(),
                        "Échec de l'installation",
                        f"Une erreur est survenue pendant l'installation de nnU-Net :\n{str(e)}"
                    )
            else:
                qt.QMessageBox.warning(
                    slicer.util.mainWindow(),
                    "Module requis manquant",
                    "Vous devez installer nnU-Net v2 pour utiliser cette extension."
                )

    def openDialog(self, which):
        """
        Ouvre une boîte de dialogue pour choisir un dossier.
        :param which: "input" pour le dossier d'entrée, "output" pour le dossier de sortie.
        """
        directory = qt.QFileDialog.getExistingDirectory(None, "Choisir un dossier", "")
        if directory:
            if which == "input":
                self.lineEditInputPath.setText(directory)
            elif which == "output":
                self.lineEditOutputPath.setText(directory)
    
    def validateCheckboxes(self, sender):
        invivoChecked = (
            self.checkBoxInvivoParenchyma.checked or
            self.checkBoxInvivoAirways.checked or
            self.checkBoxInvivoVascularTree.checked
        )
        exvivoChecked = (
            self.checkBoxExvivoParenchyma.checked or
            self.checkBoxExvivoAirways.checked
        )

        # Si les deux groupes sont sélectionnés, avertir
        if invivoChecked and exvivoChecked:
            qt.QMessageBox.warning(slicer.util.mainWindow(), "Conflit de sélection",
                                "Veuillez sélectionner uniquement Invivo ou Exvivo, pas les deux.")
            # Décocher tous sauf le dernier cliqué
            for checkbox in [
                self.checkBoxInvivoParenchyma, self.checkBoxInvivoAirways, self.checkBoxInvivoVascularTree,
                self.checkBoxExvivoParenchyma, self.checkBoxExvivoAirways
            ]:
                if checkbox != sender:
                    checkbox.setChecked(False)

    def onCheckBoxesChanged(self):
        if self.checkBoxParenchyma.checked:
            print("Segmenter parenchyme")
        if self.checkBoxAirways.checked:
            print("Segmenter voies aériennes")
        if self.checkBoxVascularTree.checked:
            print("Segmenter arbre vasculaire")
    
    def onSegmentationButtonClicked(self):
        print("Lancement de la segmentation")
