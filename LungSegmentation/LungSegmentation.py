import os
import re
import site
import textwrap
import qt
import sys
import vtk
import slicer
import platform
import subprocess
import shutil
import zipfile
import json
import tarfile
import logging
import urllib
import slicer
import tempfile
import threading
import importlib.util
from slicer.ScriptedLoadableModule import *
import importlib.resources as resources
from qt import QTimer, QTreeView, QFileSystemModel, QPushButton, QFileDialog, QMessageBox, Signal, QObject


###################################################### Objet pour les signaux permettant de savoir si la segmentation est terminée ou s'il y a une erreur ######################################################

class SegmentationSignals(QObject):
    """
    Signaux pour la segmentation
    """
    finished = Signal(bool)
    error = Signal(str)
    progress = Signal(int)

###################################################### Classe principale du module ######################################################

class LungSegmentation(ScriptedLoadableModule):
    """
    Module de segmentation des poumons
    """
    def __init__(self, parent):
        """
        Constructeur du module
        """
        parent.title = "LungSegmentation"
        parent.categories = ["Segmentation"]
        parent.contributors = ["Florian Davaux (CREATIS)"]
        parent.helpText = "Segmentation automatique des structures pulmonaires"
        parent.acknowledgementText = "Projet KOLOR SPCCT"
        self.parent = parent
        self.imagesTs_path = None
        self.parent.icon = qt.QIcon(os.path.join(os.path.dirname(__file__), 'Resources', 'Icons', 'LungSegmentation.png'))
        

####################################################### Classe pour l'interface graphique du module ######################################################

class LungSegmentationWidget(ScriptedLoadableModuleWidget):
    """
    Widget pour l'interface graphique du module de segmentation des poumons
    """
    def __init__(self, parent=None):
        """
        Constructeur du widget
        """
        ScriptedLoadableModuleWidget.__init__(self, parent)

        self.temp_dir_obj = None # Temporaire pour stocker les fichiers

        self.timer = qt.QTimer()
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.updateProgressBar)

        self.progressValue = 0
        self.progressDuration = 6 * 60  
        self.elapsedSeconds = 0

        self.signals = SegmentationSignals()
        self.signals.finished.connect(self.on_segmentation_finished)
        self.signals.error.connect(self.on_segmentation_error)

        self.input_path = None              # Chemin vers le fichier d'entrée
        self.geometry_input = None          # Geometrie du fichier d'entrée pour resampler le masque de sortie

        self.models_dir = None              # Dossier contenant les modèles téléchargés
        self.structure_to_segment = None    # Structure à segmenter
        self.tmp_file = None                # Fichier temporaire pour stocker le chemin du dataset json 
        self.name = None                    # Nom de la prédiction future

        self.convertedInputToDelete = None  # Pour suppression future

    def setup(self):
        """
        Configuration de l'interface graphique du module
        """
        self.install_dependencies_if_needed()

        ScriptedLoadableModuleWidget.setup(self)

        self.extensionPath = os.path.dirname(__file__)
        uiFilePath = os.path.join(self.extensionPath, 'Resources', 'UI', 'LungSegmentation.ui')
        
        # Chargement correct de l'UI
        uiWidget = slicer.util.loadUI(uiFilePath)
        self.layout.addWidget(uiWidget)
        self.layout.setContentsMargins(0, 0, 0, 0)

        ########################################## RABBIT ##########################################
        # IN VIVO 
        self.checkBoxRabbitInvivoParenchyma = uiWidget.findChild(qt.QCheckBox, "checkBoxRabbitInvivoParenchyma")
        self.checkBoxRabbitInvivoAirways = uiWidget.findChild(qt.QCheckBox, "checkBoxRabbitInvivoAirways")
        self.checkBoxRabbitInvivoVascularTree = uiWidget.findChild(qt.QCheckBox, "checkBoxRabbitInvivoVascularTree")
        self.checkBoxRabbitInvivoLobes = uiWidget.findChild(qt.QCheckBox, "checkBoxRabbitInvivoLobes")
        self.checkBoxRabbitInvivoParenchymaAirways = uiWidget.findChild(qt.QCheckBox, "checkBoxRabbitInvivoParenchymaAirways")
        self.checkBoxRabbitInvivoParenchymaAirwaysVascularTree = uiWidget.findChild(qt.QCheckBox, "checkBoxRabbitInvivoParenchymaAirwaysVascularTree")

        # EX VIVO 
        self.checkBoxRabbitExvivoAirways = uiWidget.findChild(qt.QCheckBox, "checkBoxRabbitExvivoAirways")
        self.checkBoxRabbitExvivoParenchymaAirways = uiWidget.findChild(qt.QCheckBox, "checkBoxRabbitExvivoParenchymaAirways")

        # AXIAL 
        self.checkBoxRabbitAxialAll = uiWidget.findChild(qt.QCheckBox, "checkBoxRabbitAxialAll")

        ########################################## PIG ##########################################

        # AXIAL
        self.checkBoxPigAxialParenchyma = uiWidget.findChild(qt.QCheckBox, "checkBoxPigAxialParenchyma")

        #########################################################################################

        self.browseInputButton = uiWidget.findChild(qt.QPushButton, "browseInputButton")
        self.lineEditInputPath = uiWidget.findChild(qt.QLineEdit, "inputLineEdit")

        self.browseOutputButton = uiWidget.findChild(qt.QPushButton, "browseOutputButton")
        self.lineEditOutputPath = uiWidget.findChild(qt.QLineEdit, "outputLineEdit")

        self.segmentationButton = uiWidget.findChild(qt.QPushButton, "pushButtonSegmentation")

        self.progressBar = uiWidget.findChild(qt.QProgressBar, "progressBar")
        self.progressBar.setVisible(False)
        self.progressBar.setValue(0)

        self.browseInputButton.clicked.connect(lambda: self.openDialog("input"))
        self.browseOutputButton.clicked.connect(lambda: self.openDialog("output"))
        self.segmentationButton.clicked.connect(self.onSegmentationButtonClicked)


    def install_dependencies_if_needed(self):
        """
        Vérifie si nnUNet_package est installé.
        Si ce n'est pas le cas, installe las bonne version puis ferme Slicer pour reload.
        """
        import importlib

        required_versions = {
            "nnUNet_package": "0.2.3"
        }

        to_install = None

        try:
            import nnUNet_package
            if nnUNet_package.__version__ != required_versions["nnUNet_package"]:
                print(f"nnUNet_package version {nnUNet_package.__version__} trouvée, {required_versions['nnUNet_package']} requise.")
                to_install = f"nnUNet_package=={required_versions['nnUNet_package']}"
            else:
                print(f"nnUNet_package {nnUNet_package.__version__} OK")
        except ImportError:
            print("nnUNet_package non installé")
            to_install = f"nnUNet_package=={required_versions['nnUNet_package']}"

        if to_install:
            msg = f"Le module {to_install} va être installé."
            msg += "\nSlicer va se fermer automatiquement après l'installation. Veuillez le relancer."
            python_exec = sys.executable
            subprocess.check_call([python_exec, "-m", "pip", "install", "--upgrade", "--no-cache-dir", to_install])
            slicer.util.mainWindow().close()
            sys.exit(0)
        else:
            print("Toutes les dépendances sont à la bonne version.")
    
    
    def openDialog(self, which):
        """
        Ouvre une boîte de dialogue pour sélectionner un fichier ou un dossier.

        Args:
            which (str): "input" pour sélectionner un fichier d'entrée, "output" pour sélectionner un dossier de sortie.
        """
        if which == "input":
            selectedPath = self.selectInputFile()
            if selectedPath:
                self.lineEditInputPath.setText(selectedPath)
        elif which == "output":
            selectedDir = qt.QFileDialog.getExistingDirectory(
                slicer.util.mainWindow(),
                "Sélectionner un dossier de sortie",
                ""
            )
            if selectedDir:
                self.lineEditOutputPath.setText(selectedDir)


    def selectInputFile(self):
        """
        Affiche une boîte de dialogue pour sélectionner un fichier image ou un dossier DICOM.
        Ne fait pas de conversion ici, juste stocke le chemin original.
        """
        optionsBox = qt.QMessageBox(slicer.util.mainWindow())
        optionsBox.setWindowTitle("Choisir une source d'image")
        optionsBox.setText("Sélectionnez le type d'entrée :")
        imageButton = optionsBox.addButton("Fichier image (.nrrd, .nii, .mha...)", qt.QMessageBox.ActionRole)
        dicomButton = optionsBox.addButton("Dossier DICOM", qt.QMessageBox.ActionRole)
        optionsBox.addButton("Annuler", qt.QMessageBox.RejectRole)
        optionsBox.exec_()

        clicked = optionsBox.clickedButton()
        if clicked == imageButton:
            path = self.handleImageSelection()
        elif clicked == dicomButton:
            path = self.handleDICOMSelection()
        else:
            return
        
        self.lineEditInputPath.setText(path)


    def safeLoadVolume(self, path):
        """
        Charge un volume de manière compatible avec les versions récentes et anciennes de Slicer.
        Retourne le node chargé ou None en cas d'échec.
        """
        node = slicer.util.loadVolume(path)
        self.geometry_input = node
        return node  # ou (node, geometryNode) si tu veux la renvoyer



    def handleImageSelection(self):
        """
        Sélectionne un fichier image, le charge dans le viewer, sans conversion immédiate.
        """
        selected = qt.QFileDialog.getOpenFileName(
            slicer.util.mainWindow(),
            "Sélectionner une image",
            "",
            "Images (*.nrrd *.nii *.nii.gz *.mha)"
        )
        if not selected:
            return None

        node = self.safeLoadVolume(selected)
        if not node:
            qt.QMessageBox.critical(slicer.util.mainWindow(), "Erreur", "Impossible de charger le fichier sélectionné.")
            return None

        return selected


    def handleDICOMSelection(self):
        """
        Sélectionne un dossier DICOM, charge le premier fichier dans le viewer, sans conversion immédiate.
        """
        dicomDir = qt.QFileDialog.getExistingDirectory(
            slicer.util.mainWindow(),
            "Sélectionner un dossier DICOM",
            ""
        )
        if not dicomDir:
            return None

        dcmFiles = [os.path.join(dicomDir, f) for f in os.listdir(dicomDir) if f.lower().endswith(".dcm")]
        if not dcmFiles:
            qt.QMessageBox.critical(slicer.util.mainWindow(), "Erreur", "Aucun fichier DICOM trouvé.")
            return None

        node = self.safeLoadVolume(dcmFiles[0])
        if not node:
            qt.QMessageBox.critical(slicer.util.mainWindow(), "Erreur", "Échec du chargement du fichier DICOM.")
            return None

        return dicomDir

    
    def prepareInputForSegmentation(self, inputPath):
        """
        Vérifie et prépare le chemin d'entrée pour la segmentation.
        Si besoin, convertit en .nrrd et retourne le chemin converti.
        """
        inputPath = inputPath.strip()
        if not inputPath or not os.path.exists(inputPath):
            raise RuntimeError("Chemin d'entrée invalide.")

        ext = os.path.splitext(inputPath)[1].lower()
        is_dir = os.path.isdir(inputPath)

        if is_dir:
            # Dossier DICOM
            dcmFiles = [os.path.join(inputPath, f) for f in os.listdir(inputPath) if f.lower().endswith(".dcm")]
            if not dcmFiles:
                raise RuntimeError("Aucun fichier DICOM trouvé dans le dossier.")
            success, volumeNode = slicer.util.loadVolume(dcmFiles[0], returnNode=True)
            if not success:
                raise RuntimeError("Erreur lors du chargement du volume DICOM.")
            convertedPath = os.path.join(slicer.app.temporaryPath, "converted_from_dicom.nrrd")
            slicer.util.saveNode(volumeNode, convertedPath)
            self.convertedInputToDelete = convertedPath
            slicer.mrmlScene.RemoveNode(volumeNode)
            return convertedPath

        elif ext in [".mha", ".nii", ".nii.gz"]:
            # Fichier image à convertir
            success, volumeNode = slicer.util.loadVolume(inputPath, returnNode=True)
            if not success:
                raise RuntimeError("Erreur lors du chargement de l'image.")
            convertedPath = os.path.join(slicer.app.temporaryPath, "converted_from_image.nrrd")
            slicer.util.saveNode(volumeNode, convertedPath)
            self.convertedInputToDelete = convertedPath
            slicer.mrmlScene.RemoveNode(volumeNode)
            return convertedPath

        elif ext == ".nrrd":
            # ✅ Aucun traitement requis
            return inputPath

        else:
            raise RuntimeError("Format non supporté. Veuillez sélectionner un fichier .nrrd, .mha, .nii, ou un dossier DICOM.")


    def check_mode(self):
        """
        Vérifie le mode de segmentation (in vivo, ex vivo ou axial).

        Return:
            str: "invivo", "exvivo" ou "axial"
        """
        if (
            self.checkBoxRabbitInvivoParenchyma.isChecked() or
            self.checkBoxRabbitInvivoAirways.isChecked() or
            self.checkBoxRabbitInvivoVascularTree.isChecked() or
            self.checkBoxRabbitInvivoLobes.isChecked() or
            self.checkBoxRabbitInvivoParenchymaAirways.isChecked() or
            self.checkBoxRabbitInvivoParenchymaAirwaysVascularTree.isChecked()
        ):
            return "invivo"
        elif self.checkBoxRabbitExvivoAirways.isChecked() or self.checkBoxRabbitExvivoParenchymaAirways.isChecked():
            return "exvivo"
        else:
            return "axial"
    

    def check_animal(self):
        """
        Vérifie l'animal à segmenter.

        Return:
            str: "pig" ou "rabbit"
        """
        if self.checkBoxPigAxialParenchyma.isChecked():
            return "pig"
        else:
            return "rabbit"
    

    def check_structure(self):
        """
        Vérifie la structure pulmonaire à segmenter.
        
        Return:
            str: "parenchyma", "airways", "vascular", "lobes", "parenchymaairways", "all"
        """
        if self.checkBoxRabbitInvivoParenchyma.isChecked() or self.checkBoxPigAxialParenchyma.isChecked():
            return "parenchyma"
        elif self.checkBoxRabbitInvivoAirways.isChecked() or self.checkBoxRabbitExvivoAirways.isChecked():
            return "airways"
        elif self.checkBoxRabbitInvivoVascularTree.isChecked():
            return "vascular"
        elif self.checkBoxRabbitInvivoLobes.isChecked():
            return "lobes"
        elif self.checkBoxRabbitInvivoParenchymaAirways.isChecked() or self.checkBoxRabbitExvivoParenchymaAirways.isChecked():
            return "parenchymaairways"
        elif self.checkBoxRabbitInvivoParenchymaAirwaysVascularTree.isChecked() or self.checkBoxRabbitAxialAll.isChecked():
            return "all"
        

    def onSegmentationButtonClicked(self):
        
        # On verifie si c'est Invivo, Exvivo ou Axial
        mode = self.check_mode()

        # On verifie si c'est Pig ou Rabbit
        animal = self.check_animal()

        # On verifie la structure à segmenter
        self.structure_to_segment = self.check_structure()
        
        print("\nLancement de la segmentation...")

        try:
            self.input_path = self.prepareInputForSegmentation(self.lineEditInputPath.text)
        except Exception as e:
            qt.QMessageBox.critical(slicer.util.mainWindow(), "Erreur d'entrée", str(e))
            return

        output_path = self.lineEditOutputPath.text

        if not os.path.isfile(self.input_path) or not self.input_path.endswith('.nrrd'):
            qt.QMessageBox.critical(slicer.util.mainWindow(), "Erreur fichier", "Veuillez sélectionner un fichier NRRD valide en entrée.")
            return

        extension_dir = os.path.dirname(__file__)
        self.models_dir = os.path.join(extension_dir, "models")

        self.progressBar.setVisible(True)
        self.progressBar.setValue(0)
        self.progressValue = 0
        self.elapsedSeconds = 0

        qt.QTimer.singleShot(0, self.timer.start)

        self.start_segmentation(mode, output_path, animal)
    
    def start_segmentation(self, mode, output_path, animal):
        """
        Fonction qui lance le processus de segmentation en arrière-plan.
        
        Elle appelle le script nnunet_runner.py avec les paramètres de la segmentation.
        Elle attend que le processus se termine, puis emet le signal finished si tout se passe bien,
        ou le signal error si un problème se produit.
        
        Args:
            mode (str): Mode de segmentation (In vivo, Ex vivo)
            input_path (str): Chemin vers le fichier d'entrée
            output_path (str): Chemin vers le dossier de sortie
            animal (str): Nom de l'animal
        """
        def worker():
            """
            Fonction worker qui lance le processus de segmentation en arrière-plan.
            
            Elle appelle le script nnunet_runner.py avec les paramètres de la segmentation.
            Elle attend que le processus se termine, puis emet le signal finished si tout se passe bien,
            ou le signal error si un problème se produit.
            """
            try:
                from pathlib import Path
                runner_path = Path(__file__).parent/"scripts"/"nnunet_runner.py"

                # Fichier temporaire pour stocker le chemin du dataset json
                self.tmp_file = os.path.join(tempfile.gettempdir(), "nnunet_context.json")
                if os.path.exists(self.tmp_file):
                    os.remove(self.tmp_file)
                
                cmd = [
                    sys.executable, str(runner_path),
                    "--mode", mode,
                    "--structure", self.structure_to_segment,
                    "--input", self.input_path,
                    "--output", output_path,
                    "--models_dir", self.models_dir,
                    "--animal", animal,
                    "--tmp_file", self.tmp_file
                ]
                subprocess.run(cmd, text=True)
                self.signals.finished.emit(True)
            except subprocess.CalledProcessError as e:
                self.signals.error.emit(str(e))

        threading.Thread(target=worker, daemon=True).start()


    def on_segmentation_error(self, error_message):
        """
        Fonction appelée en cas d'erreur lors de la segmentation.
        Elle arrête le timer, met à jour la barre de progression et affiche un message d'erreur.
        
        Args:
            error_message (str): Message d'erreur à afficher.
        """
        self.timer.stop()
        self.progressBar.setVisible(False)
        slicer.util.errorDisplay(f"Erreur lors de la segmentation :\n{error_message}")


    def on_segmentation_finished(self, success):
        """
        Fonction appelée lorsque la segmentation est terminée.
        Elle arrête le timer, met à jour la barre de progression et affiche un message de succès.
        
        Args:
            success (bool): Indique si la segmentation a réussi ou non.
        """
        self.timer.stop()
        self.progressBar.setValue(100)
        self.progressBar.setVisible(False)

        if success:
            self.load_prediction(self.lineEditOutputPath.text)
            slicer.util.infoDisplay("Segmentation terminée avec succès.")


    def updateProgressBar(self):
        """
        Met à jour la barre de progression toutes les secondes.
        Si la durée de progression est dépassée, la barre est bloquée à 99% tant que la segmentation n'est pas finie.
        """
        if self.elapsedSeconds >= self.progressDuration:
            self.progressBar.setValue(99)
            return
        
        self.elapsedSeconds += 1
        progress = int((self.elapsedSeconds / self.progressDuration) * 99)
        self.progressBar.setValue(progress)


    def load_prediction(self, output_path):
        """
        Charge la prédiction générée par nnUNet dans Slicer.

        Args:
            output_path (str): Chemin du dossier de sortie où la prédiction est enregistrée.
        """
        prediction_path = os.path.join(output_path, "001.nrrd")
        if not os.path.exists(prediction_path):
            qt.QMessageBox.warning(slicer.util.mainWindow(), "Erreur", "Aucune prédiction trouvée à charger.")
            return
        else:
            seg_name = self.structure_to_segment
            self.convert_prediction_to_segmentation(prediction_path, output_path, seg_name)


    def convert_prediction_to_segmentation(self, prediction_path, output_path, segmentation_name):
        """
        Convertit une prédiction nnUNet en segmentation Slicer et renomme les segments selon les noms dans dataset.json.
        
        Args:
            prediction_path (str): Chemin du fichier de prédiction (.nrrd).
            output_path (str): Chemin du dossier de sortie pour la segmentation.
            labelmap_name (str): Nom du labelmap à créer.
            segmentation_name (str): Nom de la segmentation à créer.
        """

        # Charger la prédiction comme labelmap
        labelmapNode = slicer.util.loadLabelVolume(prediction_path)
        labelmapNode.SetName(segmentation_name)

        # # Créer la segmentation
        # segmentationNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", segmentation_name)

        # referenceVolumeNode = slicer

        # segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(referenceVolumeNode)

        # Importer le labelmap dans la segmentation
        # slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(labelmapNode, segmentationNode)

        segmentationNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", segmentation_name)
        segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(self.geometry_input)

        print("Size of geometry input: ", self.geometry_input.GetImageData().GetDimensions())

        with open(self.tmp_file, 'r') as f:
            data = json.load(f)
        
        dataset_json_path = data["dataset_json_path"]

        # Charger le dataset.json du modèle
        with open(dataset_json_path, "r") as f:
            dataset = json.load(f)

        # labels = { "lobe_inf_d": 1, ... } → inverse pour avoir {1: "lobe_inf_d"}
        raw_label_map = dataset.get("labels", {})
        label_map = {int(v): k for k, v in raw_label_map.items() if int(v) > 0}

        # Renommer les segments
        segment_ids = vtk.vtkStringArray()
        segmentationNode.GetSegmentation().GetSegmentIDs(segment_ids)

        for i in range(segment_ids.GetNumberOfValues()):
            segment_id = segment_ids.GetValue(i)
            segment = segmentationNode.GetSegmentation().GetSegment(segment_id)

            label_index = i + 1 
            name = label_map.get(label_index, f"Classe_{label_index}")
            segment.SetName(name)

        # Sauvegarder la segmentation
        segmentation_path = os.path.join(output_path, segmentation_name + ".nrrd")
        slicer.util.saveNode(segmentationNode, segmentation_path)

        # slicer.mrmlScene.RemoveNode(labelmapNode)

        # Suppression de l'ancienne prédiction si elle existe
        if os.path.exists(prediction_path):
            os.remove(prediction_path)
        
        if self.convertedInputToDelete and os.path.exists(self.convertedInputToDelete):
            os.remove(self.convertedInputToDelete)