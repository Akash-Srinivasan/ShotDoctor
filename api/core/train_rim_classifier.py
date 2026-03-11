#!/usr/bin/env python3
"""
Train YOLOv8n-cls Rim Classifier

This script trains a YOLOv8n-cls (nano classification) model on rim-area crops
to determine if a ball passed through the hoop (made vs missed vs uncertain).

Usage:
    python train_rim_classifier.py
    python train_rim_classifier.py --data rim_classifier_data --epochs 100
    python train_rim_classifier.py --batch 64 --imgsz 160

Requirements:
    pip install ultralytics torch
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

import torch


def verify_device():
    """
    Verify GPU/MPS availability and select the best device.

    Returns:
        str: Device string ("mps", "cuda", or "cpu")
    """
    print("\n" + "-" * 60)
    print("DEVICE VERIFICATION")
    print("-" * 60)
    print(f"PyTorch version: {torch.__version__}")

    if torch.backends.mps.is_available():
        print("✓ MPS (Apple Silicon) available")
        # Quick MPS test
        try:
            x = torch.randn(100, 100, device="mps")
            _ = x @ x
            torch.mps.synchronize()
            print("  MPS test: PASSED")
            device = "mps"
        except Exception as e:
            print(f"  MPS test: FAILED - {e}")
            print("  Falling back to CPU")
            device = "cpu"
    elif torch.cuda.is_available():
        print(f"✓ CUDA available: {torch.cuda.get_device_name(0)}")
        print(f"  CUDA version: {torch.version.cuda}")
        print(f"  GPU memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
        device = "cuda"
    else:
        print("⚠ No GPU available, using CPU (training will be slower)")
        device = "cpu"

    print("-" * 60 + "\n")
    return device


def check_dataset(data_path):
    """
    Check if the dataset exists and print class distribution.

    Args:
        data_path: Path to dataset directory

    Returns:
        bool: True if dataset is valid, False otherwise
    """
    data_path = Path(data_path)

    if not data_path.exists():
        print(f"❌ Dataset directory not found: {data_path}")
        print("\nPlease run prepare_rim_classifier_data.py first to create the dataset.")
        return False

    # Check for required directories (train and valid)
    train_dir = data_path / "train"
    val_dir = data_path / "valid"
    if not val_dir.exists():
        val_dir = data_path / "val"  # Also accept "val"

    if not train_dir.exists() or not val_dir.exists():
        print(f"❌ Missing train or valid directory in: {data_path}")
        print("\nExpected structure (from prepare_rim_classifier_data.py):")
        print("  rim_classifier_data/")
        print("    train/")
        print("      ball_through_hoop/")
        print("      ball_not_through_hoop/")
        print("    valid/")
        print("      ball_through_hoop/")
        print("      ball_not_through_hoop/")
        return False

    # Print class distribution
    print("\n" + "=" * 60)
    print("DATASET OVERVIEW")
    print("=" * 60)
    print(f"Dataset path: {data_path.absolute()}")

    for split_name, split_dir in [("train", train_dir), ("valid", val_dir)]:
        print(f"\n{split_name.upper()} SET:")

        total_images = 0
        for class_dir in sorted(split_dir.iterdir()):
            if class_dir.is_dir():
                count = len(list(class_dir.glob("*.jpg"))) + len(list(class_dir.glob("*.png")))
                total_images += count
                print(f"  {class_dir.name:24s}: {count:5d} images")

        print(f"  {'Total':12s}: {total_images:5d} images")

    print("=" * 60 + "\n")
    return True


def train_classifier(data_path, epochs, batch_size, img_size, device, output_path):
    """
    Train YOLOv8n-cls on rim classifier data.

    Args:
        data_path: Path to dataset directory
        epochs: Number of training epochs
        batch_size: Batch size for training
        img_size: Input image size
        device: Device to train on ("mps", "cuda", or "cpu")
        output_path: Path to save the trained model

    Returns:
        Path to the best trained model
    """
    from ultralytics import YOLO

    print("\n" + "=" * 60)
    print("LOADING BASE MODEL")
    print("=" * 60)

    # Load pre-trained ImageNet classification model
    base_model_path = Path(__file__).parent / "yolov8n-cls.pt"

    if not base_model_path.exists():
        print(f"Base model not found at: {base_model_path}")
        print("Downloading yolov8n-cls.pt from Ultralytics...")
        model = YOLO("yolov8n-cls.pt")  # Will auto-download
    else:
        print(f"Loading base model from: {base_model_path}")
        model = YOLO(str(base_model_path))

    print("✓ Base model loaded")

    # Training configuration
    print("\n" + "=" * 60)
    print("TRAINING CONFIGURATION")
    print("=" * 60)
    print(f"Dataset:       {data_path}")
    print(f"Epochs:        {epochs}")
    print(f"Batch size:    {batch_size}")
    print(f"Image size:    {img_size}")
    print(f"Device:        {device}")
    print(f"Optimizer:     AdamW")
    print(f"Learning rate: 0.001")
    print(f"Patience:      15 (early stopping)")
    print("=" * 60 + "\n")

    # Train the model
    print("Starting training...\n")

    results = model.train(
        data=str(Path(data_path).absolute()),
        epochs=epochs,
        batch=batch_size,
        imgsz=img_size,
        device=device,
        optimizer="AdamW",
        lr0=0.001,
        patience=15,
        project="rim_classifier",
        name="yolov8n_rim_cls",
        exist_ok=True,
        verbose=True,
    )

    # Get best model path
    best_model = Path("rim_classifier/yolov8n_rim_cls/weights/best.pt")

    if not best_model.exists():
        print("❌ Training failed - best.pt not found")
        return None

    print(f"\n✓ Training complete!")
    print(f"✓ Best model saved to: {best_model}")

    return best_model


def validate_classifier(model_path, data_path):
    """
    Validate the trained classifier and print metrics.

    Args:
        model_path: Path to trained model
        data_path: Path to dataset directory

    Returns:
        Validation results
    """
    from ultralytics import YOLO

    print("\n" + "=" * 60)
    print("VALIDATING MODEL")
    print("=" * 60)

    model = YOLO(str(model_path))
    results = model.val(data=str(Path(data_path).absolute()))

    # Print validation metrics
    print("\n" + "=" * 60)
    print("VALIDATION RESULTS")
    print("=" * 60)

    # Overall accuracy
    accuracy = results.top1
    top5_accuracy = results.top5

    print(f"Top-1 Accuracy: {accuracy:.1%}")
    print(f"Top-5 Accuracy: {top5_accuracy:.1%}")

    # Per-class metrics (if available)
    if hasattr(results, 'confusion_matrix') and results.confusion_matrix is not None:
        cm = results.confusion_matrix.matrix
        class_names = ["ball_through_hoop", "ball_not_through_hoop"]

        print("\nPer-Class Metrics:")
        for i, class_name in enumerate(class_names):
            if i < len(cm):
                # True positives, false positives, false negatives
                tp = cm[i, i]
                fp = cm[:, i].sum() - tp
                fn = cm[i, :].sum() - tp

                precision = tp / (tp + fp) if (tp + fp) > 0 else 0
                recall = tp / (tp + fn) if (tp + fn) > 0 else 0

                print(f"  {class_name:12s}: Precision={precision:.1%}, Recall={recall:.1%}")

    # Target metrics
    print("\n" + "-" * 60)
    print("TARGET METRICS:")
    print(f"  Accuracy:          {'✓ PASS' if accuracy >= 0.85 else '✗ FAIL'} (target: ≥85%, actual: {accuracy:.1%})")

    # Calculate false positive rate (missed classified as made)
    if hasattr(results, 'confusion_matrix') and results.confusion_matrix is not None:
        cm = results.confusion_matrix.matrix
        if len(cm) >= 2:
            # False positives: missed frames classified as made
            fp_rate = cm[1, 0] / cm[1, :].sum() if cm[1, :].sum() > 0 else 0
            print(f"  False Positive Rate: {'✓ PASS' if fp_rate < 0.15 else '✗ FAIL'} (target: <15%, actual: {fp_rate:.1%})")

    print("=" * 60 + "\n")

    return results


def export_model(model_path, output_path):
    """
    Copy the trained model to the specified output path.

    Args:
        model_path: Path to trained best.pt
        output_path: Destination path for the model

    Returns:
        Path to exported model
    """
    output_path = Path(output_path)

    print("\n" + "=" * 60)
    print("EXPORTING MODEL")
    print("=" * 60)

    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Copy model
    shutil.copy(model_path, output_path)

    print(f"✓ Model exported to: {output_path.absolute()}")
    print("\nTo use in your code:")
    print(f'  from ultralytics import YOLO')
    print(f'  model = YOLO("{output_path.name}")')
    print(f'  results = model(rim_crop_image)')
    print("=" * 60 + "\n")

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Train YOLOv8n-cls Rim Classifier",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument(
        "--data",
        type=str,
        default="rim_classifier_data",
        help="Path to dataset directory (created by prepare_rim_classifier_data.py)"
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=50,
        help="Number of training epochs"
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=32,
        help="Batch size for training"
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=128,
        help="Input image size (rim crops are small)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output path for trained model (default: api/core/rim_classifier_model.pt)"
    )

    args = parser.parse_args()

    # Set default output path if not provided
    if args.output is None:
        args.output = str(Path(__file__).parent / "rim_classifier_model.pt")

    print("\n" + "=" * 60)
    print("  YOLOv8n-cls RIM CLASSIFIER TRAINING")
    print("=" * 60 + "\n")

    # Step 1: Verify device
    print("STEP 1: Checking device availability...")
    device = verify_device()

    # Step 2: Check dataset
    print("STEP 2: Verifying dataset...")
    if not check_dataset(args.data):
        sys.exit(1)

    # Step 3: Train model
    print("STEP 3: Training classifier...")
    model_path = train_classifier(
        data_path=args.data,
        epochs=args.epochs,
        batch_size=args.batch,
        img_size=args.imgsz,
        device=device,
        output_path=args.output
    )

    if model_path is None:
        print("❌ Training failed")
        sys.exit(1)

    # Step 4: Validate model
    print("STEP 4: Validating classifier...")
    validate_classifier(model_path, args.data)

    # Step 5: Export model
    print("STEP 5: Exporting model...")
    final_path = export_model(model_path, args.output)

    # Summary
    print("\n" + "=" * 60)
    print("  TRAINING COMPLETE!")
    print("=" * 60)
    print(f"\nYour rim classifier is ready at:")
    print(f"  {final_path.absolute()}")
    print("\nNext steps:")
    print("  1. Integrate the model into your shot analysis pipeline")
    print("  2. Test with rim crop images from real videos")
    print("  3. Monitor accuracy and adjust if needed")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
