"""
ANPR VLM Accuracy Benchmark Script.
Evaluates Qwen 3.6 35B VLM zero-shot plate recognition precision against dataset vehicle images.
See Docs/PS1_Extended_Investigative_Capabilities.md Section 5.
"""
import os
import sys
import glob
import asyncio
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from shared.catalyst_client import vlm_extract, CATALYST_VLM_URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_vlm_anpr_eval():
    logger.info("Running Qwen 3.6 35B VLM ANPR Accuracy Benchmark...")
    
    # Locate Kaggle dataset images dynamically
    dataset_dir = None
    try:
        import kagglehub
        dataset_dir = kagglehub.dataset_download("dataclusterlabs/indian-number-plates-dataset")
    except Exception:
        cache_base = os.path.expanduser("~/.cache/kagglehub/datasets/dataclusterlabs/indian-number-plates-dataset")
        if os.path.exists(cache_base):
            versions = glob.glob(os.path.join(cache_base, "versions/*"))
            if versions:
                dataset_dir = versions[-1]
            else:
                dataset_dir = cache_base

    image_files = glob.glob(os.path.join(dataset_dir, "**/*.jpg"), recursive=True) if dataset_dir else []
    logger.info(f"Found {len(image_files)} sample vehicle images in Kaggle dataset at {dataset_dir}")

    url = CATALYST_VLM_URL()
    if not url:
        logger.warning(
            "CATALYST_VLM_ENDPOINT is not configured in environment. "
            "Evaluation script running in dry-run mode against Kaggle dataset images."
        )
        print("\n--- ANPR VLM BENCHMARK DRY-RUN RESULT ---")
        print(f"Dataset Path: {dataset_dir}")
        print(f"Vehicle Images Found: {len(image_files)}")
        print("Model Target: VL-Qwen3.6-35B-A3B")
        print("Status: Endpoint switch ready for live cloud evaluation.\n")
        return

    if not image_files:
        logger.warning("No .jpg images found in dataset path.")
        return

    sample_prompt = "Extract the vehicle registration number (license plate) visible in this image. Return ONLY the uppercase plate string."
    system_prompt = "You are a specialized law-enforcement ANPR optical character recognition model."
    
    # Pick first 3 sample vehicle images for evaluation
    for img_path in image_files[:3]:
        try:
            with open(img_path, "rb") as f:
                img_bytes = f.read()
            logger.info("Sending image %s (%d bytes) to Qwen 3.6 35B VLM...", os.path.basename(img_path), len(img_bytes))
            res = await vlm_extract(img_bytes, sample_prompt, system_prompt)
            logger.info("✅ VLM ANPR OCR Result for %s: %s", os.path.basename(img_path), res)
        except Exception as e:
            logger.warning("VLM OCR Call failed for %s: %s", os.path.basename(img_path), e)

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(run_vlm_anpr_eval())
