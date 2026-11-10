# 🎙️ Sri Diya Audio-Only Voice Assistant & Gemini AI Studio

An e-commerce voice application powered by **Python**, **Streamlit**, and **Google Gemini Live Native Audio** (`gemini-2.5-flash-native-audio-latest`).

---

## 🌟 Key Features

### 🎙️ Audio-Only Product Voice Assistant
- **🔇 100% Voice Interaction**: Interacts exclusively through voice audio. Zero on-screen product cards, images, written details, or textual responses are displayed.
- **📦 Strictly Grounded in Product Catalog (`mergeProduct`)**:
  - `Lotus Mala | Thamarai Mani Malai (108 Beads)` (ID #6)
  - `Navaratna Gemstone Mala | Navarathna Malai (108 Beads)` (ID #7)
  - `Rudraksha Mala (108 beads, 6 mm)` (ID #13)
  - `Ruthra Sakthi Vilva Mala` (ID #52)
  - `Gomti Chakra Mala (35 Beads)` (ID #169)
  - `Tiger Eye Stone Mala (108 Beads, 6 mm)` (ID #180)
- **⚡ Spoken Dynamic Data**: Speaks live pricing (MRP vs selling price), discounts, dynamic stock availability, cart status, delivery timelines, and benefits.
- **🗣️ Conversational Audio**: Generates natural spoken audio scripts without markdown asterisks or bullet clutter.
- **🎛️ Full Audio Controller**: Speak/Play, Pause, Resume, Stop (rewind to 0:00), Replay, scrubbable timeline, elapsed timer, volume slider, and animated waveform.

### 🎙️ Custom Tamil Voice Studio
- Convert any custom Tamil text into natural spoken speech using Gemini Live native audio voices.

### 💬 General Gemini AI Chat
- Full streaming multi-turn chat assistant.

---

## 🚀 Quick Start

Run either command:

```bash
python chat-bot.py
```
*or*
```bash
streamlit run chat-bot.py
```

Open **`http://localhost:8501`** in your browser.
Enter your Gemini API key in the left sidebar and start speaking with the assistant!
