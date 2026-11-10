"""
Streamlit application entry point alias.
You can run:
    streamlit run app.py
or:
    streamlit run chat-bot.py
or:
    python chat-bot.py
"""
import runpy
from pathlib import Path

target_file = Path(__file__).parent / "chat-bot.py"
runpy.run_path(str(target_file), run_name="__main__")

