"""
FunctionGemma Router - Routes user prompts to appropriate functions.
Supports 8 functions: 5 actions, 1 context, 2 passthrough.
"""

import os
import warnings

# Suppress transformers warnings before importing
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
warnings.filterwarnings("ignore", message=".*generation flags are not valid.*")

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, logging as transformers_logging
from transformers.utils import get_json_schema
from typing import Tuple, Dict, Any
import time
import re
import json

# Suppress transformers logging
transformers_logging.set_verbosity_error()

from src.utils.config import Config

# Debug flag - set to True to see Gemma's raw response
DEBUG_ROUTER = True


# --- Tool Definitions ---

def set_timer(duration: str, label: str = None) -> str:
    """
    Set a countdown timer.
    
    Args:
        duration: Duration like '5 minutes' or '1 hour'
        label: Optional label for the timer
    """
    return "result"

def set_alarm(time: str, label: str = None) -> str:
    """
    Set an alarm for a specific time.
    
    Args:
        time: Time for alarm like '7am' or '14:30'
        label: Optional label
    """
    return "result"

def create_calendar_event(title: str, date: str = None, time: str = None, duration: int = None) -> str:
    """
    Create a calendar event.
    
    Args:
        title: Event title
        date: Date like 'tomorrow' or '2024-01-15'
        time: Time like '3pm'
        duration: Duration in minutes
    """
    return "result"

def add_task(text: str, priority: str = None) -> str:
    """
    Add a task to the to-do list.
    
    Args:
        text: Task description
        priority: Priority level
    """
    return "result"

def web_search(query: str) -> str:
    """
    Search the web for information using DuckDuckGo.
    Returns up to 5 search results including titles, snippets, and URLs.
    
    Use this when the user asks to:
    - Search for information online
    - Look up current events or news
    - Find facts, definitions, or explanations
    - Research a topic
    
    Args:
        query: Search query string (e.g., "Python programming best practices")
    
    Returns:
        Search results with titles, body snippets (200 chars), and URLs
    """
    return "result"

def get_system_info() -> str:
    """
    Get comprehensive current system state snapshot.
    
    Returns information about:
    - Current time and date
    - Active countdown timers (label, remaining time)
    - Upcoming alarms (time, label)
    - Today's calendar events (title, time)
    - Pending tasks from to-do list (text, completion status)
    - Current weather (temperature, condition, high/low)
    - Recent news headlines (title, category, URL)
    
    Use this when the user asks:
    - "What's on my schedule today?"
    - "What's my current status?"
    - "What do I have coming up?"
    - "Give me a summary of everything"
    - Questions about their timers, tasks, or calendar
    """
    return "result"

def thinking(prompt: str) -> str:
    """
    Use for complex queries requiring reasoning, math, coding, or multi-step analysis.
    
    Args:
        prompt: The user's original prompt
    """
    return "result"

def nonthinking(prompt: str) -> str:
    """
    Use for simple queries, greetings, factual questions not requiring deep reasoning.
    
    Args:
        prompt: The user's original prompt
    """
    return "result"


# Pre-compute tool schemas
TOOLS = [
    get_json_schema(set_timer),
    get_json_schema(set_alarm),
    get_json_schema(create_calendar_event),
    get_json_schema(add_task),
    get_json_schema(web_search),
    get_json_schema(get_system_info),
    get_json_schema(thinking),
    get_json_schema(nonthinking),
]

SYSTEM_MSG = "You are a model that can do function calling with the following functions"

# All valid function names
VALID_FUNCTIONS = {
    "set_timer", "set_alarm", "create_calendar_event",
    "add_task", "web_search", "get_system_info", "thinking", "nonthinking"
}


def ensure_model_available(model_path: str = None) -> str:
    """
    Ensure the router model is available locally.

    Returns:
        str: Path to the model
    """
    if model_path is None:
        model_path = Config.FUNCTION_GEMMA_PATH

    if os.path.exists(model_path) and os.path.isdir(model_path):
        # Check for essential files
        if os.path.exists(os.path.join(model_path, "model.safetensors")):
            return model_path

    raise RuntimeError(
        f"Router model not found at {model_path}\n"
        f"Please download the model and place it in: {model_path}"
    )


class FunctionGemmaRouter:
    """Routes user prompts to appropriate functions using fine-tuned FunctionGemma."""
    
    def __init__(self, model_path: str = None, compile_model: bool = False):
        # Ensure model is available (download from HF if needed)
        model_path = ensure_model_available(model_path)
        
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Loading FunctionGemma Router on {device.upper()}...")
        start = time.time()
        
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        
        # CPU often doesn't support bfloat16 natively
        dtype = torch.bfloat16 if device == "cuda" else torch.float32
        
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype=dtype,
            device_map=device,
        )
        self.model.eval()

        
        # Compile for speed (PyTorch 2.0+)
        if compile_model:
            try:
                self.model = torch.compile(self.model, mode="reduce-overhead")
                print("Model compiled with torch.compile()")
            except Exception as e:
                print(f"torch.compile() not available: {e}")
        
        print(f"Router loaded in {time.time() - start:.2f}s")
        print(f"Device: {self.model.device}, Dtype: {self.model.dtype}")
    
    @torch.inference_mode()
    def route(self, user_prompt: str) -> Tuple[str, Dict[str, Any]]:
        """
        Route a user prompt to the appropriate function.
        
        Returns:
            Tuple of (function_name, arguments_dict)
        """
        # Build messages
        messages = [
            {"role": "developer", "content": SYSTEM_MSG},
            {"role": "user", "content": user_prompt},
        ]
        
        # Apply chat template
        prompt = self.tokenizer.apply_chat_template(
            messages,
            tools=TOOLS,
            add_generation_prompt=True,
            tokenize=False
        )
        
        # Tokenize
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
        
        # Generate with minimal settings for speed
        outputs = self.model.generate(
            **inputs,
            max_new_tokens=100,  # Increased for function args
            do_sample=False,
            use_cache=True,
            pad_token_id=self.tokenizer.pad_token_id,
        )
        
        # Decode new tokens only
        new_tokens = outputs[0][inputs['input_ids'].shape[1]:]
        response = self.tokenizer.decode(new_tokens, skip_special_tokens=False)
        
        # Debug: Print raw Gemma response
        if DEBUG_ROUTER:
            print(f"\n{'='*50}")
            print(f"[Router DEBUG] User prompt: {user_prompt}")
            print(f"[Router DEBUG] Raw Gemma response:")
            print(f"  {repr(response)}")
            print(f"{'='*50}")
        
        # Parse function call
        return self._parse_function_call(response, user_prompt)
    
    def _parse_function_call(self, response: str, user_prompt: str) -> Tuple[str, Dict[str, Any]]:
        """Parse the model's response to extract function name and arguments."""
        
        # Try to find function call pattern: call:function_name
        for func_name in VALID_FUNCTIONS:
            if f"call:{func_name}" in response:
                # Try to extract arguments
                args = self._extract_arguments(response, func_name, user_prompt)
                return func_name, args
        
        # Fallback to nonthinking if no function found
        return "nonthinking", {"prompt": user_prompt}
    
    def _extract_arguments(self, response: str, func_name: str, user_prompt: str) -> Dict[str, Any]:
        """Extract arguments from the response."""
        
        # Default arguments for passthrough functions
        if func_name in ("thinking", "nonthinking"):
            return {"prompt": user_prompt}
        
        # For get_system_info, no args needed
        if func_name == "get_system_info":
            return {}
        
        # Parse the model's custom format: {key:<escape>value<escape>,key2:<escape>value2<escape>}
        # Find the arguments block after the function name
        pattern = rf"call:{func_name}\{{([^}}]+)\}}"
        match = re.search(pattern, response)
        
        if match:
            args_str = match.group(1)
            args = {}
            
            # Split by comma, but handle values with commas inside <escape> tags
            # Pattern: key:<escape>value<escape> OR key:value (for ints/bools)
            # We look for key followed by either <escape>...<escape> OR anything until comma/end
            arg_pattern = r'(\w+):(?:<escape>([^<]*)<escape>|([^,]+))'
            for arg_match in re.finditer(arg_pattern, args_str):
                key = arg_match.group(1)
                # group(2) is escaped value, group(3) is unescaped value
                val_escaped = arg_match.group(2)
                val_unescaped = arg_match.group(3)
                
                value = val_escaped if val_escaped is not None else val_unescaped
                
                # Try to convert to appropriate type
                if value.isdigit():
                    args[key] = int(value)
                elif value.lower() in ('true', 'false'):
                    args[key] = value.lower() == 'true'
                else:
                    args[key] = value
            
            if args:
                return args
        
        # Fallback: return user prompt as main argument
        if func_name == "set_timer":
            return {"duration": user_prompt}
        elif func_name == "set_alarm":
            return {"time": user_prompt}
        elif func_name == "create_calendar_event":
            return {"title": user_prompt}
        elif func_name == "add_task":
            return {"text": user_prompt}
        elif func_name == "web_search":
            return {"query": user_prompt}
        
        return {}
    
    def route_with_timing(self, user_prompt: str) -> Tuple[Tuple[str, Dict], float]:
        """Route with timing info."""
        start = time.time()
        result = self.route(user_prompt)
        elapsed = time.time() - start
        return result, elapsed


if __name__ == "__main__":
    from rich.console import Console
    console = Console()

    router = FunctionGemmaRouter(compile_model=False)

    test_prompts = [
        # Timer functions
        ("Set a timer for 10 minutes", "set_timer"),
        ("Start a 30 second timer", "set_timer"),
        ("Timer for 2 hours please", "set_timer"),

        # Alarm functions
        ("Wake me up at 7am", "set_alarm"),
        ("Set an alarm for 6:30", "set_alarm"),

        # Calendar functions
        ("Schedule meeting tomorrow at 3pm", "create_calendar_event"),
        ("Add dentist appointment next Monday", "create_calendar_event"),
        ("Create event for lunch at noon", "create_calendar_event"),

        # Task management
        ("Add buy groceries to my list", "add_task"),
        ("Remember to call mom", "add_task"),
        ("Add finish report to my tasks", "add_task"),

        # Web search
        ("Search for Italian recipes", "web_search"),
        ("Look up weather in Tokyo", "web_search"),
        ("Find Python tutorials", "web_search"),

        # Context/System info
        ("How much time is left on my timer?", "get_system_info"),
        ("What's on my calendar today?", "get_system_info"),
        ("Show me my tasks", "get_system_info"),
        ("What's my schedule?", "get_system_info"),

        # Passthrough - thinking
        ("Explain quantum computing", "thinking"),
        ("Write a Python function to sort a list", "thinking"),
        ("How does photosynthesis work?", "thinking"),

        # Passthrough - nonthinking
        ("Hello there!", "nonthinking"),
        ("What's the capital of France?", "nonthinking"),
        ("Good morning", "nonthinking"),
    ]

    console.print("\n" + "="*70)
    console.print("[bold cyan]FUNCTION CALLING ROUTER TEST[/bold cyan]")
    console.print("="*70)
    
    total_time = 0
    correct = 0
    
    for prompt, expected in test_prompts:
        (func_name, args), elapsed = router.route_with_timing(prompt)
        total_time += elapsed
        match = "✓" if func_name == expected else "✗"
        if func_name == expected:
            correct += 1
            # Green for correct
            console.print(f"\n[bold green][{match}] {prompt}[/bold green]")
            console.print(f"    → [green]{func_name}({args})[/green] [dim][{elapsed*1000:.0f}ms][/dim]")
        else:
            # Red for wrong
            console.print(f"\n[bold red][{match}] {prompt}[/bold red]")
            console.print(f"    → [red]{func_name}({args})[/red] [yellow](expected: {expected})[/yellow] [dim][{elapsed*1000:.0f}ms][/dim]")
    
    avg_time = total_time / len(test_prompts)
    console.print(f"\n{'='*70}")
    accuracy_pct = 100*correct/len(test_prompts)
    accuracy_color = "green" if accuracy_pct >= 80 else "yellow" if accuracy_pct >= 60 else "red"
    console.print(f"[{accuracy_color}]Accuracy: {correct}/{len(test_prompts)} ({accuracy_pct:.0f}%)[/{accuracy_color}]")
    console.print(f"Average routing time: [cyan]{avg_time*1000:.0f}ms[/cyan] per prompt")
    console.print(f"Total time: [cyan]{total_time:.2f}s[/cyan] for {len(test_prompts)} prompts")