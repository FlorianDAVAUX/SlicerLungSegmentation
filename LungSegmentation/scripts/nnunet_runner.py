if __name__ == "__main__":
    import argparse
    import sys
    from pathlib import Path
    from nnUNet_package.predict import run_nnunet_prediction

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True)
    parser.add_argument("--structure", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--models_dir", required=True)
    parser.add_argument("--name", default="prediction")
    args = parser.parse_args()

    run_nnunet_prediction(
        mode=args.mode,
        structure=args.structure,
        input_path=args.input,
        output_dir=args.output,
        models_dir=args.models_dir,
        name=args.name
    )
