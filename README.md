# 🫁 LungSegmentation

<p align="center">
  <img src="Resources/Icons/LungSegmentation.png" alt="Logo" width="200"/>
</p>

**LungSegmentation** est une extension pour [3D Slicer](https://www.slicer.org/) permettant la **segmentation automatique des structures pulmonaires** (parenchyme, voies aériennes, arbre vasculaire) à partir d’images médicales (DICOM ou NRRD), à l’aide d’un modèle **nnU-Netv2** pré-entraîné.

---

## ✨ Fonctionnalités

- ✅ Segmentation du **parenchyme**, des **voies aériennes** et des **vaisseaux**
- ✅ Support des données **in-vivo** et **ex-vivo**
- ✅ Chargement direct des résultats dans Slicer après prédiction

---

## 🛠️ Installation

### Depuis le Extension Manager (recommandé)

1. Ouvrez **3D Slicer**
2. Allez dans le **Extension Manager**
3. Recherchez **LungSegmentation**
4. Cliquez sur **Install**
5. Redémarrez Slicer

### Depuis le code source

```bash
git clone https://github.com/FlorianDAVAUX/LungSegmentation.git
```

---

## 🧩 Structures segmentables et combinaisons possibles
L’extension LungSegmentation permet de segmenter trois types de structures pulmonaires à partir d’images in-vivo ou ex-vivo :

|Type d'Image | Parenchyme | Voies aériennes | Arbre Vasculaire |  Parenchyme + Voies aériennes | Parenchyme + Arbre Vasculaire | Voies aériennes + Arbre Vasculaire | Parenchyme + Voies aériennes + Arbre Vasculaire |
|-------------|------------|-----------------|------------------|-------------------------------|-------------------------------|------------------------------------|-------------------------------------------------|
| In vivo     |  ✅        | ✅              | ✅              | ✅                            | ❌                            | ❌                                |  ✅                                             | 
| Ex vivo     | ❌        | ✅              | ❌             | ✅                            | ❌                            | ❌                                 |     ❌                                           | 

---

## ⚠️ Limitations importantes
Les vaisseaux ne sont disponibles que pour les images in-vivo
Les images ex-vivo ne permettent de segmenter que le parenchyme
Il est possible de segmenter plusieurs structures à la fois, tant qu’elles sont compatibles avec le type d’image sélectionné




