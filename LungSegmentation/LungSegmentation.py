import os
import re
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

        self.extracted_model_path = None
        self.customPythonPath = None
        self.prediction = None
        self.modified_dataset_json = None

        self.convertedInputToDelete = None  # pour suppression future
        self.originalInputPath = None  # pour affichage dans le champ de texte
        self.convertedInputPath = None  # fichier .nrrd converti à utiliser en interne



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

        # Récupération des widgets
        self.checkBoxInvivoParenchyma = uiWidget.findChild(qt.QCheckBox, "checkBoxInvivoParenchyma")
        self.checkBoxInvivoAirways = uiWidget.findChild(qt.QCheckBox, "checkBoxInvivoAirways")
        self.checkBoxInvivoVascularTree = uiWidget.findChild(qt.QCheckBox, "checkBoxInvivoVascularTree")
        self.checkBoxInvivoLobes = uiWidget.findChild(qt.QCheckBox, "checkBoxInvivoLobes")

        self.checkBoxExvivoParenchyma = uiWidget.findChild(qt.QCheckBox, "checkBoxExvivoParenchyma")
        self.checkBoxExvivoAirways = uiWidget.findChild(qt.QCheckBox, "checkBoxExvivoAirways")

        self.browseInputButton = uiWidget.findChild(qt.QPushButton, "browseInputButton")
        self.lineEditInputPath = uiWidget.findChild(qt.QLineEdit, "inputLineEdit")

        self.browseOutputButton = uiWidget.findChild(qt.QPushButton, "browseOutputButton")
        self.lineEditOutputPath = uiWidget.findChild(qt.QLineEdit, "outputLineEdit")

        self.segmentationButton = uiWidget.findChild(qt.QPushButton, "pushButtonSegmentation")

        self.progressBar = uiWidget.findChild(qt.QProgressBar, "progressBar")
        self.progressBar.setVisible(False)
        self.progressBar.setValue(0)

        # Connexions
        for checkbox in [self.checkBoxInvivoParenchyma, self.checkBoxInvivoAirways, self.checkBoxInvivoVascularTree, self.checkBoxInvivoLobes,
                 self.checkBoxExvivoParenchyma, self.checkBoxExvivoAirways]:
            checkbox.toggled.connect(lambda state, cb=checkbox: self.validateCheckboxes(cb))

        self.browseInputButton.clicked.connect(lambda: self.openDialog("input"))
        self.browseOutputButton.clicked.connect(lambda: self.openDialog("output"))
        self.segmentationButton.clicked.connect(self.onSegmentationButtonClicked)
    
    
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

        if path:
            self.originalInputPath = path
            self.lineEditInputPath.setText(path)


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

        # Charger le volume dans le viewer, peu importe l’extension
        success, loadedNode = slicer.util.loadVolume(selected, returnNode=True)
        if not success:
            qt.QMessageBox.critical(slicer.util.mainWindow(), "Erreur", "Impossible de charger le fichier sélectionné.")
            return None

        return selected


    def handleDICOMSelection(self):
        """
        Sélectionne un dossier DICOM, charge le premier fichier dans le viewer sans conversion immédiate.
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

        success, _ = slicer.util.loadVolume(dcmFiles[0], returnNode=True)
        if not success:
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
            return convertedPath

        elif ext in [".mha", ".nii", ".nii.gz"]:
            # Fichier image à convertir
            success, volumeNode = slicer.util.loadVolume(inputPath, returnNode=True)
            if not success:
                raise RuntimeError("Erreur lors du chargement de l'image.")
            convertedPath = os.path.join(slicer.app.temporaryPath, "converted_from_image.nrrd")
            slicer.util.saveNode(volumeNode, convertedPath)
            self.convertedInputToDelete = convertedPath
            return convertedPath

        elif ext == ".nrrd":
            # ✅ Aucun traitement requis
            return inputPath

        else:
            raise RuntimeError("Format non supporté. Veuillez sélectionner un fichier .nrrd, .mha, .nii, ou un dossier DICOM.")



    def validateCheckboxes(self, sender):
        """
        Valide les cases à cocher pour s'assurer qu'il n'y a pas de sélection mixte Invivo/Exvivo
        et que les combinaisons de structures sont valides.
        
        Args:
            sender: La case à cocher qui a été modifiée
        """
        # Grouper les cases par type
        invivo_checkboxes = {
            "parenchyma": self.checkBoxInvivoParenchyma,
            "airways": self.checkBoxInvivoAirways,
            "vascular": self.checkBoxInvivoVascularTree,
            "lobes": self.checkBoxInvivoLobes
        }

        exvivo_checkboxes = {
            "parenchyma": self.checkBoxExvivoParenchyma,
            "airways": self.checkBoxExvivoAirways
        }

        # État des groupes
        invivo_checked = any(cb.checked for cb in invivo_checkboxes.values())
        exvivo_checked = any(cb.checked for cb in exvivo_checkboxes.values())

        # 1. Empêcher la sélection mixte Invivo/Exvivo
        if invivo_checked and exvivo_checked:
            qt.QMessageBox.warning(
                slicer.util.mainWindow(), "Conflit de sélection",
                "Veuillez sélectionner uniquement Invivo **ou** Exvivo, pas les deux."
            )
            # Désactiver toutes les cases sauf celle qui vient d'être cochée
            for cb in list(invivo_checkboxes.values()) + list(exvivo_checkboxes.values()):
                if cb != sender:
                    cb.setChecked(False)
            return


    def check_combination_and_warn_invivo(self, parenchyma_checked: bool, airways_checked: bool, vascular_checked: bool, lobes_checked: bool) -> bool:
        """
        Vérifie la combinaison des cases à cocher et affiche un avertissement si la combinaison est invalide.

        Args:
            parenchyma_checked: booléen indiquant si la case Parenchyme est cochée
            airways_checked: booléen indiquant si la case Airways est cochée
            vascular_checked: booléen indiquant si la case Vascular Tree est cochée
            lobes_checked: booléen indiquant si la case Lobes est cochée

        Return:
            True si la combinaison est valide, False sinon
        """
        total_checked = parenchyma_checked + airways_checked + vascular_checked + lobes_checked

        # Cas valides
        if total_checked == 1:
            return True
        if lobes_checked and (parenchyma_checked or airways_checked or vascular_checked):
            valid = False
        elif parenchyma_checked and airways_checked and not vascular_checked and not lobes_checked:
            valid = True
        elif parenchyma_checked and airways_checked and vascular_checked and not lobes_checked:
            valid = True
        else:
            valid = False

        if valid:
            return True

        # Cas invalides → pop-up
        msgBox = QMessageBox()
        msgBox.setIcon(QMessageBox.Warning)
        msgBox.setText("La combinaison sélectionnée n'est pas autorisée.")
        msgBox.setInformativeText(
            "Combinaisons autorisées en in vivo:\n"
            "• Lobes seuls\n"
            "• Parenchyme seul\n"
            "• Airways seul\n"
            "• Vascular seul\n"
            "• Parenchyme + Airways\n"
            "• Parenchyme + Airways + Vascular"
        )
        msgBox.setWindowTitle("Combinaison invalide")
        msgBox.setStandardButtons(QMessageBox.Ok)
        msgBox.exec_()

        return False


    def check_combination_and_warn_exvivo(self, parenchyma_checked: bool, airways_checked: bool) -> bool:
        """
        Vérifie la combinaison des cases à cocher pour Exvivo et affiche un avertissement si la combinaison est invalide.
        
        Args:
            parenchyma_checked: booléen indiquant si la case Parenchyme est cochée
            airways_checked: booléen indiquant si la case Airways est cochée
        Return:
            True si la combinaison est valide, False sinon
        """
       
        total_checked = parenchyma_checked + airways_checked

        # Cas valides
        if parenchyma_checked or airways_checked:
            valid = True
        elif airways_checked:
            valid = True
        elif parenchyma_checked:
            valid = False
        else:
            valid = False

        if valid:
            return True

        # Cas invalides → pop-up
        msgBox = QMessageBox()
        msgBox.setIcon(QMessageBox.Warning)
        msgBox.setText("La combinaison sélectionnée n'est pas autorisée.")
        msgBox.setInformativeText(
            "Combinaisons autorisées en ex vivo:\n"
            "• Airways seul\n"
            "• Parenchyme + Airways"
        )
        msgBox.setWindowTitle("Combinaison invalide")
        msgBox.setStandardButtons(QMessageBox.Ok)
        msgBox.exec_()

        return False


    def loadConfig(self):
        """
        Charge la configuration des modèles depuis le fichier JSON.
        """
        config_path = os.path.join(os.path.dirname(__file__), 'Resources', 'models.json')
        with open(config_path, 'r') as f:
            return json.load(f)
    

    def onSegmentationButtonClicked(self):
        """
        Fonction appelée lors du clic sur le bouton de segmentation.
        Elle vérifie les cases à cocher, charge la configuration, télécharge le modèle si nécessaire,
        prépare les chemins d'entrée et de sortie, et lance la segmentation.
        """
        config = self.loadConfig()

        mode = "Invivo" if self.checkBoxInvivoParenchyma.isChecked() or self.checkBoxInvivoAirways.isChecked() or self.checkBoxInvivoVascularTree.isChecked() or self.checkBoxInvivoLobes.isChecked() else "Exvivo"

        if mode == "Invivo":
            if not self.check_combination_and_warn_invivo(
                self.checkBoxInvivoParenchyma.isChecked(),
                self.checkBoxInvivoAirways.isChecked(),
                self.checkBoxInvivoVascularTree.isChecked(),
                self.checkBoxInvivoLobes.isChecked()
            ):
                return
        else:
            if not self.check_combination_and_warn_exvivo(
                self.checkBoxExvivoParenchyma.isChecked(),
                self.checkBoxExvivoAirways.isChecked()
            ):
                return

        if mode == "Invivo":
            if self.checkBoxInvivoParenchyma.isChecked() and self.checkBoxInvivoAirways.isChecked() and self.checkBoxInvivoVascularTree.isChecked():
                selected_key = "All"
            elif self.checkBoxInvivoParenchyma.isChecked() and self.checkBoxInvivoAirways.isChecked():
                selected_key = "ParenchymaAirways"
            elif self.checkBoxInvivoParenchyma.isChecked():
                selected_key = "Parenchyma"
            elif self.checkBoxInvivoAirways.isChecked():
                selected_key = "Airways"
            elif self.checkBoxInvivoVascularTree.isChecked():
                selected_key = "Vascular"
            elif self.checkBoxInvivoLobes.isChecked():
                selected_key = "Lobes"
            else:
                qt.QMessageBox.warning(slicer.util.mainWindow(), "Aucun modèle sélectionné", "Veuillez sélectionner au moins une structure.")
                return
        else: 
            if self.checkBoxExvivoParenchyma.isChecked() and self.checkBoxExvivoAirways.isChecked():
                selected_key = "ParenchymaAirways"
            elif self.checkBoxExvivoAirways.isChecked():
                selected_key = "Airways"
            else:
                qt.QMessageBox.warning(slicer.util.mainWindow(), "Modèle indisponible", "Seule la combinaison Parenchyme + Airways est supportée en Exvivo.")
                return

        try:
            model_info = config[mode][selected_key]
        except KeyError:
            qt.QMessageBox.critical(slicer.util.mainWindow(), "Erreur de configuration", f"Aucune configuration trouvée pour {mode} > {selected_key}")
            return
        
        print("\n📣 Lancement de la segmentation...")

        model_url = model_info["model_url"]
        dataset_id = model_info["model_id"]
        configuration = model_info["configuration"]
        fold = str(model_info["fold"])
        model_name = model_info["model_name"]

        try:
            input_nrrd_path = self.prepareInputForSegmentation(self.lineEditInputPath.text)
        except Exception as e:
            qt.QMessageBox.critical(slicer.util.mainWindow(), "Erreur d'entrée", str(e))
            return

        output_path = self.lineEditOutputPath.text

        self.temp_dir_obj = tempfile.TemporaryDirectory()
        temp_path = self.temp_dir_obj.name

        model_zip_path = os.path.join(temp_path, model_name + ".zip")
        self.extracted_model_path = os.path.join(temp_path, model_name)

        if not os.path.exists(model_zip_path):
            print("\n🔽 Téléchargement du modèle depuis GitHub...")
            urllib.request.urlretrieve(model_url, model_zip_path)
            print("\n✅ Modèle téléchargé")

        if not os.path.exists(self.extracted_model_path):
            with zipfile.ZipFile(model_zip_path, 'r') as zip_ref:
                zip_ref.extractall(self.extracted_model_path)

        if not os.path.isfile(input_nrrd_path) or not input_nrrd_path.endswith('.nrrd'):
            qt.QMessageBox.critical(slicer.util.mainWindow(), "Erreur fichier", "Veuillez sélectionner un fichier NRRD valide en entrée.")
            return

        self.edit_json_for_prediction(input_nrrd_path)

        os.environ["nnUNet_results"] = os.path.abspath(self.extracted_model_path)

        self.progressBar.setVisible(True)
        self.progressBar.setValue(0)
        self.progressValue = 0
        self.elapsedSeconds = 0

        qt.QTimer.singleShot(0, self.timer.start)

        threading.Thread(
            target=self.run_segmentation_in_thread,
            args=(self.imagesTs_path, output_path, dataset_id, configuration, fold),
        ).start()
    

    def run_segmentation_in_thread(self, input_path, output_path, dataset_id, configuration, fold):
        """
        Fonction exécutée dans un thread secondaire pour lancer la segmentation.
        Elle prépare l'environnement, exécute la commande de segmentation et gère les sorties.

        Args:
            input_path (str): Chemin du fichier d'entrée (.nrrd).
            output_path (str): Chemin du dossier de sortie pour les résultats de segmentation.
            dataset_id (str): Identifiant du dataset pour la segmentation.
            configuration (str): Configuration du modèle à utiliser pour la segmentation.
            fold (str): Numéro de fold à utiliser pour la segmentation.
        """
        
        command = [
            "nnUNetv2_predict",
            "-i", input_path,
            "-o", output_path,
            "-d", dataset_id,
            "-c", configuration,
            "-f", fold,
        ]

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            universal_newlines=True
        )

        for line in process.stdout:
            print(line, end='')
        
        # Wait for the process to finish
        process.stdout.close()
        return_code = process.wait()

        if return_code != 0:
            self.signals.error.emit("❌ Erreur simulée")
        else:
            self.signals.finished.emit(True)

    
    def install_dependencies_if_needed(self):
        """
        Vérifie si numpy==1.26.4, blosc2==2.5.1 et nnunetv2 sont installés.
        Si ce n'est pas le cas, installe les bonnes versions puis ferme Slicer pour reload.
        """
        import importlib

        required_versions = {
            "numpy": "1.26.4",
            "blosc2": "2.5.1",
            "nnunetv2": None,
        }

        to_install = []

        # Check numpy
        try:
            import numpy
            if numpy.__version__ != required_versions["numpy"]:
                print(f"❌ numpy version {numpy.__version__} trouvée, {required_versions['numpy']} requise.")
                to_install.append(f"numpy=={required_versions['numpy']}")
            else:
                print(f"✅ numpy {numpy.__version__} OK")
        except ImportError:
            print("❌ numpy non installé")
            to_install.append(f"numpy=={required_versions['numpy']}")

        # Check blosc2
        try:
            import blosc2
            if blosc2.__version__ != required_versions["blosc2"]:
                print(f"❌ blosc2 version {blosc2.__version__} trouvée, {required_versions['blosc2']} requise.")
                to_install.append(f"blosc2=={required_versions['blosc2']}")
            else:
                print(f"✅ blosc2 {blosc2.__version__} OK")
        except ImportError:
            print("❌ blosc2 non installé")
            to_install.append(f"blosc2=={required_versions['blosc2']}")

        # Check nnunetv2
        try:
            nnunetv2_spec = importlib.util.find_spec("nnunetv2")
            if nnunetv2_spec is None:
                raise ImportError
            print("✅ nnunetv2 OK")
        except ImportError:
            print("❌ nnunetv2 non installé")
            to_install.append("nnunetv2")

        if to_install:
            msg = "Les dépendances suivantes vont être installées ou mises à jour :\n" + "\n".join(to_install)
            msg += "\n\nSlicer va se fermer automatiquement après l'installation. Veuillez le relancer."
            qt.QMessageBox.information(
                slicer.util.mainWindow(), "Installation des dépendances", msg
            )
            python_exec = sys.executable
            for pkg in to_install:
                subprocess.check_call([python_exec, "-m", "pip", "install", "--upgrade", "--no-cache-dir", pkg])
            slicer.util.mainWindow().close()
            sys.exit(0)
        else:
            print("✅ Toutes les dépendances sont à la bonne version.")
    

    def on_segmentation_error(self, error_message):
        """
        Fonction appelée en cas d'erreur lors de la segmentation.
        Elle arrête le timer, met à jour la barre de progression et affiche un message d'erreur.
        
        Args:
            error_message (str): Message d'erreur à afficher.
        """
        self.timer.stop()
        self.progressBar.setVisible(False)
        slicer.util.errorDisplay(f"❌ Erreur lors de la segmentation :\n{error_message}")


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
            slicer.util.infoDisplay("✅ Segmentation terminée avec succès.")
                
        # Après avoir copié ou converti la prédiction finale
        self.clean_auxiliary_files(self.lineEditInputPath.text)   
        self.clean_auxiliary_files(self.lineEditOutputPath.text)

    
    def clean_auxiliary_files(self, path):
        for filename in ["dataset.json", "plans.json", "predict_from_raw_data_args.json"]:
            file_path = os.path.join(path, filename)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    print(f"⚠️ Impossible de supprimer {filename} : {e}")


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
        prediction_file = os.path.join(output_path, "001.nrrd")

        if not prediction_file:
            qt.QMessageBox.warning(slicer.util.mainWindow(), "Erreur", "Aucune prédiction trouvée à charger.")
            return
        else:
            seg_name = self.get_segmentation_name()
            self.convert_prediction_to_segmentation(prediction_file, output_path, labelmap_name=seg_name, segmentation_name=seg_name)


    def convert_prediction_to_segmentation(self, prediction_path, output_path, labelmap_name="segmentation", segmentation_name="segmentation"):
        """
        Convertit une prédiction nnUNet en segmentation Slicer et renomme les segments selon les noms dans dataset.json.
        
        Args:
            prediction_path (str): Chemin du fichier de prédiction (.nrrd).
            output_path (str): Chemin du dossier de sortie pour la segmentation.
            labelmap_name (str): Nom du labelmap à créer.
            segmentation_name (str): Nom de la segmentation à créer.
        """

        # Charger la prédiction comme labelmap
        [success, labelmapNode] = slicer.util.loadLabelVolume(prediction_path, returnNode=True)
        if not success:
            raise RuntimeError(f"Échec du chargement de la prédiction : {prediction_path}")
        labelmapNode.SetName(labelmap_name)

        # Créer la segmentation node
        segmentationNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", segmentation_name)
        slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(labelmapNode, segmentationNode)

        # Lire les noms des labels depuis dataset.json
        if not hasattr(self, "modified_dataset_json") or not os.path.exists(self.modified_dataset_json):
            raise RuntimeError("Le fichier dataset.json modifié n'a pas été trouvé.")

        with open(self.modified_dataset_json, 'r') as f:
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

        # Nettoyage
        slicer.mrmlScene.RemoveNode(labelmapNode)

        # Suppression de l'ancienne prédiction si elle existe
        if os.path.exists(prediction_path):
            os.remove(prediction_path)
        
        if os.path.exists(self.convertedInputToDelete):
            os.remove(self.convertedInputToDelete)


    def get_segmentation_name(self):
        """
        Retourne le nom de la segmentation basé sur les cases à cocher sélectionnées.
        Si aucune case n'est cochée, retourne "Segmentation".
        Returns:
            str: Nom de la segmentation.
        """
        structures = []

        if self.checkBoxInvivoParenchyma.isChecked() or self.checkBoxExvivoParenchyma.isChecked():
            structures.append("parenchyma")
        if self.checkBoxInvivoAirways.isChecked() or self.checkBoxExvivoAirways.isChecked():
            structures.append("airways")
        if self.checkBoxInvivoVascularTree.isChecked():
            structures.append("vascular_tree")
        if self.checkBoxInvivoLobes.isChecked():
            structures.append("lobes")

        if not structures:
            return "Segmentation"

        return "_".join(structures)


    def edit_json_for_prediction(self, input_image_path):
        """
        Modifie le fichier dataset.json pour préparer la prédiction.

        Args:
            extracted_model_path (str): Chemin du dossier contenant le modèle extrait.
            input_image_path (str): Chemin du fichier d'image d'entrée à utiliser pour la prédiction.
        """
        json_path = None
        for root, dirs, files in os.walk(self.extracted_model_path):
            if "dataset.json" in files:
                json_path = os.path.abspath(os.path.join(root, "dataset.json"))
                break
        if not json_path:
            raise FileNotFoundError("dataset.json non trouvé")

        # Charger le dataset.json
        with open(json_path, 'r') as f:
            dataset = json.load(f)

        # Supprimer la section training et mettre numTraining à 0
        dataset.pop("training", None)
        dataset["numTraining"] = 0

        # Vérifier que le fichier input_image_path existe et est une image NRRD
        if not os.path.isfile(input_image_path) or not input_image_path.endswith('.nrrd'):
            raise ValueError("Le chemin d'entrée n'est pas un fichier .nrrd valide.")

        # Créer le dossier imagesTs
        imagesTs_path = os.path.join(os.path.dirname(json_path), "imagesTs")
        os.makedirs(imagesTs_path, exist_ok=True)

        # Copier l'image dans imagesTs avec le nom attendu
        new_filename = "001_0000.nrrd"
        dst = os.path.join(imagesTs_path, new_filename)
        shutil.copyfile(input_image_path, dst)
        print(f"\n 📂 Copié {os.path.basename(input_image_path)} → imagesTs/{new_filename}")

        # Ajouter la section test
        dataset["numTest"] = 1
        dataset["test"] = [[f"./imagesTs/{new_filename}"]]

        # Sauvegarder
        with open(json_path, 'w') as f:
            json.dump(dataset, f, indent=4)

        # Stockage pour prédiction
        self.modified_dataset_json = json_path
        self.imagesTs_path = imagesTs_path 
