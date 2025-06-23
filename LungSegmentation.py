import os
import qt
import slicer
import subprocess
import shutil
import zipfile
import json
import logging
import urllib
import sys
import slicer
import tempfile
import threading
from qt import QTimer
from slicer.ScriptedLoadableModule import *
from qt import QTreeView, QFileSystemModel, QPushButton, QFileDialog, QMessageBox, Signal, QObject


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

        self.timer = qt.QTimer()
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.updateProgressBar)

        self.progressValue = 0
        self.progressDuration = 5 * 60  
        self.elapsedSeconds = 0

        self.tempConvertedPath = None  # Pour stocker le chemin du fichier temporaire converti


        self.signals = SegmentationSignals()
        self.signals.finished.connect(self.on_segmentation_finished)
        self.signals.error.connect(self.on_segmentation_error)


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
    
    
    def install_dependencies_if_needed(self):
        """
        Vérifie si les dépendances nécessaires sont installées et propose de les installer si elles manquent.
        """
        required_packages = {
            "torch": "torch",
            "numpy": "numpy",
            "scikit-learn": "sklearn",
            "SimpleITK": "SimpleITK",
            "nibabel": "nibabel",
            "tqdm": "tqdm",
            "blosc2": "blosc2",
            "acvl-utils": "acvl_utils",
            "nnunetv2": "nnunetv2"
        }

        missing_packages = []

        # Vérification de l'importabilité des modules
        for pip_name, import_name in required_packages.items():
            try:
                module = __import__(import_name)
            except ImportError:
                missing_packages.append(pip_name)

        if not missing_packages:
            print("✅ Tous les paquets requis sont installés.")
            return

        # Afficher la boîte de dialogue pour installation
        install = qt.QMessageBox.question(
            slicer.util.mainWindow(),
            "Modules manquants",
            f"Les modules suivants sont manquants :\n{', '.join(missing_packages)}\nVoulez-vous les installer maintenant ?",
            qt.QMessageBox.Yes | qt.QMessageBox.No
        )
        if install == qt.QMessageBox.Yes:
            try:
                python_exec = sys.executable
                print(sys.executable)
                for pkg in missing_packages:
                    subprocess.check_call([python_exec, "-m", "pip", "install", pkg])
                qt.QMessageBox.information(
                    slicer.util.mainWindow(), "Installation réussie",
                    "Les dépendances manquantes ont été installées avec succès."
                )
            except subprocess.CalledProcessError as e:
                qt.QMessageBox.critical(
                    slicer.util.mainWindow(), "Échec de l'installation",
                    f"Erreur pendant l'installation :\n{str(e)}"
                )
        else:
            qt.QMessageBox.warning(
                slicer.util.mainWindow(), "Modules manquants",
                "Vous devez installer les dépendances pour utiliser cette extension."
            )


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
        Gère les conversions nécessaires vers le format .nrrd.
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
            return self.handleImageSelection()
        elif clicked == dicomButton:
            return self.handleDICOMSelection()
        return None

    def handleImageSelection(self):
        """
        Gère la sélection d'un fichier image, convertit si nécessaire et retourne le chemin du fichier sélectionné.
        """
        selected = qt.QFileDialog.getOpenFileName(
            slicer.util.mainWindow(),
            "Sélectionner une image",
            "",
            "Images (*.nrrd *.nii *.nii.gz *.mha)"
        )
        if not selected:
            return None

        ext = os.path.splitext(selected)[1].lower()
        if ext in [".nii", ".nii.gz", ".mha"]:
            try:
                print(f"\n🔄 Conversion de {selected} en .nrrd...")
                loadedNode = slicer.util.loadVolume(selected, returnNode=True)[1]
                if not loadedNode:
                    raise RuntimeError("Le fichier n'a pas pu être chargé.")

                extension_dir = os.path.dirname(os.path.abspath(__file__))
                converted_nrrd_path = os.path.join(extension_dir, "converted_input.nrrd")
                slicer.util.saveNode(loadedNode, converted_nrrd_path)
                print(f"\n✅ Conversion terminée : {converted_nrrd_path}")

                self.tempConvertedPath = converted_nrrd_path  # ← stocké pour suppression plus tard
                return converted_nrrd_path
            except Exception as e:
                qt.QMessageBox.critical(slicer.util.mainWindow(), "Erreur de conversion", f"Erreur lors de la conversion en .nrrd : {str(e)}")
                return None
        else:
            slicer.util.loadVolume(selected)
        self.tempConvertedPath = None
        return selected


    def handleDICOMSelection(self):
        """
        Gère la sélection d'un dossier DICOM, charge le volume DICOM et le convertit en .nrrd.
        Retourne le chemin du fichier converti ou None en cas d'erreur.
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

        success, volumeNode = slicer.util.loadVolume(dcmFiles[0], returnNode=True)
        if success:
            outputPath = os.path.join(dicomDir, "converted_volume.nrrd")
            slicer.util.saveNode(volumeNode, outputPath)
            return outputPath
        else:
            qt.QMessageBox.critical(slicer.util.mainWindow(), "Erreur", "Échec du chargement du volume DICOM.")
            return None


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


    def check_combination_and_warn(self, parenchyme_checked: bool, airways_checked: bool, vascular_checked: bool, lobes_checked: bool) -> bool:
        """
        Vérifie la combinaison des cases à cocher et affiche un avertissement si la combinaison est invalide.

        Args:
            parenchyme_checked: booléen indiquant si la case Parenchyme est cochée
            airways_checked: booléen indiquant si la case Airways est cochée
            vascular_checked: booléen indiquant si la case Vascular Tree est cochée
            lobes_checked: booléen indiquant si la case Lobes est cochée

        Return:
            True si la combinaison est valide, False sinon
        """
        total_checked = parenchyme_checked + airways_checked + vascular_checked + lobes_checked

        # Cas valides
        if total_checked == 1:
            return True
        if lobes_checked and (parenchyme_checked or airways_checked or vascular_checked):
            valid = False
        elif parenchyme_checked and airways_checked and not vascular_checked and not lobes_checked:
            valid = True
        elif parenchyme_checked and airways_checked and vascular_checked and not lobes_checked:
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
            "Combinaisons autorisées :\n"
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
        if not self.check_combination_and_warn(
            self.checkBoxInvivoParenchyma.isChecked(),
            self.checkBoxInvivoAirways.isChecked(),
            self.checkBoxInvivoVascularTree.isChecked(),
            self.checkBoxInvivoLobes.isChecked()
        ):
            return

        print("\n📣 Lancement de la segmentation...")

        config = self.loadConfig()

        mode = "Invivo" if self.checkBoxInvivoParenchyma.isChecked() or self.checkBoxInvivoAirways.isChecked() or self.checkBoxInvivoVascularTree.isChecked() or self.checkBoxInvivoLobes.isChecked() else "Exvivo"

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

        model_url = model_info["model_url"]
        model_id = model_info["model_id"]
        configuration = model_info["configuration"]
        fold = str(model_info["fold"])
        model_name = model_info["model_name"]

        input_path = self.lineEditInputPath.text 
        output_path = self.lineEditOutputPath.text

        temp_path = slicer.app.temporaryPath if slicer.app.temporaryPath else tempfile.gettempdir()
        model_zip_path = os.path.join(temp_path, model_name + ".zip")
        extracted_model_path = os.path.join(temp_path, model_name)

        if not os.path.exists(model_zip_path):
            print("\n🔽 Téléchargement du modèle depuis GitHub...")
            urllib.request.urlretrieve(model_url, model_zip_path)
            print("\n✅ Modèle téléchargé")

        if not os.path.exists(extracted_model_path):
            with zipfile.ZipFile(model_zip_path, 'r') as zip_ref:
                zip_ref.extractall(extracted_model_path)

        # Ici on part du principe que input_path est un fichier NRRD
        if not os.path.isfile(input_path) or not input_path.endswith('.nrrd'):
            qt.QMessageBox.critical(slicer.util.mainWindow(), "Erreur fichier", "Veuillez sélectionner un fichier NRRD valide en entrée.")
            return

        self.edit_json_for_prediction(extracted_model_path, input_path)

        os.environ["nnUNet_results"] = os.path.abspath(extracted_model_path)

        # Lancement de la prédiction
        self.progressBar.setVisible(True)
        self.progressBar.setValue(0)
        self.progressValue = 0
        self.elapsedSeconds = 0
        self.timer.start()

        # threading.Thread(
        #     target=self.run_segmentation_in_thread,
        #     args=(self.imagesTs_path, output_path, model_id, configuration, fold)
        # ).start()

        self.load_prediction(self.lineEditOutputPath.text)
    

    def run_segmentation_in_thread(self, input_path, output_path, model_id, configuration, fold):
        """
        Exécute la segmentation dans un thread séparé pour éviter de bloquer l'interface utilisateur.
        
        Args:
            input_path (str): Chemin du fichier d'entrée.
            output_path (str): Chemin du dossier de sortie.
            model_id (str): ID du modèle à utiliser pour la segmentation.
            configuration (str): Configuration du modèle.
            fold (str): Fold à utiliser pour la segmentation.
        """
        command = [
            "nnUNetv2_predict",
            "-i", input_path,
            "-o", output_path,
            "-d", model_id,
            "-c", configuration,
            "-f", fold,
        ]

        self.progressBar.setValue(0)
        self.progressBar.setVisible(True)

        try:
            subprocess.run(command, check=True)
            self.signals.finished.emit(True)
        except subprocess.CalledProcessError as e:
            self.signals.error.emit(str(e))
        
    
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

        if self.tempConvertedPath:
            if os.path.exists(self.tempConvertedPath):
                try:
                    os.remove(self.tempConvertedPath)
                    print(f"🗑️ Fichier temporaire supprimé : {self.tempConvertedPath}")
                except Exception as e:
                    print(f"⚠️ Erreur lors de la suppression : {e}")
            self.tempConvertedPath = None


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


    # def load_prediction(self, output_path):
    #     """
    #     Charge la prédiction générée par nnUNet dans Slicer.

    #     Args:
    #         output_path (str): Chemin du dossier de sortie où la prédiction est enregistrée.
    #     """
    #     prediction_file = os.path.join(output_path, "001.nrrd")
    #     new_path = os.path.join(output_path, "segmentation.nrrd")
    #     os.rename(prediction_file, new_path)
    #     self.convert_prediction_to_segmentation(new_path)

    #     if not prediction_file:
    #         qt.QMessageBox.warning(slicer.util.mainWindow(), "Erreur", "Aucune prédiction trouvée à charger.")
    #         return
        
    #     loadedNode = slicer.util.loadLabelVolume(new_path)
    #     if loadedNode:
    #         print(f"✅ Chargé dans Slicer : {new_path}")
    #     else:
    #         print(f"❌ Échec du chargement : {new_path}")

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
            self.convert_prediction_to_segmentation(prediction_file, output_path)


    def convert_prediction_to_segmentation(self, prediction_path, output_path, labelmap_name="segmentation", segmentation_name="segmentation"):
        """
        Convertit une prédiction nnUNet en segmentation Slicer.
        """

        [success, labelmapNode] = slicer.util.loadLabelVolume(prediction_path, returnNode=True)
        if not success:
            raise RuntimeError(f"Échec du chargement de la prédiction : {prediction_path}")
        labelmapNode.SetName(labelmap_name)

        segmentationNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", segmentation_name)
        slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(labelmapNode, segmentationNode)

        segmentation_path = os.path.join(output_path, segmentation_name + ".nrrd")

        # Sauvegarder la segmentation (par défaut en .nrrd)
        slicer.util.saveNode(segmentationNode, segmentation_path)

        slicer.mrmlScene.RemoveNode(labelmapNode)


    def edit_json_for_prediction(self, extracted_model_path, input_image_path):
        """
        Modifie le fichier dataset.json pour préparer la prédiction.

        Args:
            extracted_model_path (str): Chemin du dossier contenant le modèle extrait.
            input_image_path (str): Chemin du fichier d'image d'entrée à utiliser pour la prédiction.
        """
        json_path = None
        for root, dirs, files in os.walk(extracted_model_path):
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