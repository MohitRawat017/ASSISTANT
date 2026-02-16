import os 
from dotenv import load_dotenv 
from huggingface_hub import snapshot_download
from transformers import AutoProcessor, AutoTokenizer, AutoModelForCausalLM

def download_model(model_id, cache_dir, model_type):
    """
    Download a model from Hugging Face using snapshot_download for consistency.
    """
    print(f"\n--- Starting download for {model_type.upper()}: {model_id} ---")
    
    try:
        if model_type == "asr":
            # Using snapshot_download ensures we get the weights and the processor
            snapshot_download(
                repo_id=model_id,
                local_dir=cache_dir,
                local_dir_use_symlinks=False
            )
        elif model_type == "llm":
            # Specifically for GGUF models
            snapshot_download(
                repo_id=model_id,
                local_dir=cache_dir,
                allow_patterns=["*Q6_K_L.gguf"],
                local_dir_use_symlinks=False
            )
        # elif model_type == "llm":
        #     AutoTokenizer.from_pretrained(model_id, cache_dir=cache_dir)
        #     AutoModelForCausalLM.from_pretrained(model_id, cache_dir=cache_dir)
        elif model_type == "tts":
            snapshot_download(
                repo_id=model_id,
                local_dir=cache_dir,
                local_dir_use_symlinks=False
            )
        elif model_type == "tool_call":
            snapshot_download(
                repo_id=model_id,
                local_dir=cache_dir,
                local_dir_use_symlinks=False
            )
        else:
            raise ValueError(f"Unknown model type: {model_type}")
            
        print(f"Successfully downloaded {model_id} to {cache_dir}")
        
    except Exception as e:
        print(f"Error downloading {model_id}: {str(e)}")

def get_model_folder_name(model_id):
    """
    Extract a clean folder name from the model ID.
    Example: 'deepdml/faster-whisper-large-v3-turbo-ct2' -> 'faster-whisper-large-v3-turbo-ct2'
    """
    return model_id.split('/')[-1]

def main():
    load_dotenv()
    hf_token = os.getenv("HF_TOKEN")
    
    if not hf_token:
        print("Warning: HF_TOKEN not found in .env. Some models may require authentication.")
    else:
        os.environ["HUGGINGFACE_HUB_TOKEN"] = hf_token
    
    # Optimized transfer if hf_transfer is installed
    os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
    
    BASE_DIR = os.path.abspath("models")
    
    MODELS = [
        {
            "id": "deepdml/faster-whisper-large-v3-turbo-ct2",
            "type": "asr",
        },
        {
            "id": "Systran/faster-distil-whisper-medium.en",
            "type": "asr",
        },
        {
            "id": "bartowski/Llama-3.2-3B-Instruct-GGUF", 
            "type": "llm",
        },
        {
            # "id": "hexgrad/Kokoro-82M",
            # "id": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
            "id": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
            "type": "tts",
        },
        {
            "id": "nlouis/pocket-ai-router",
            "type": "tool_call",
        }
    ]
    
    for model in MODELS:
        # Create the type directory (e.g., models/asr, models/llm, models/tts)
        type_dir = os.path.join(BASE_DIR, model['type'])
        
        # Create the specific model directory (e.g., models/asr/faster-whisper-large-v3-turbo-ct2)
        model_folder_name = get_model_folder_name(model['id'])
        model_dir = os.path.join(type_dir, model_folder_name)
        
        os.makedirs(model_dir, exist_ok=True)
        
        download_model(
            model_id=model['id'],
            cache_dir=model_dir,
            model_type=model['type']
        )

if __name__ == "__main__":
    main()
