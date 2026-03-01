# Dexy

Production-grade DexScreener token intelligence monitor with adaptive strategies.

Dexy monitors DexScreener for token events and sends Telegram alerts based on configurable strategy rules.

---

## 🚀 Features

- Real-time DexScreener monitoring  
- Configurable strategy engine (`strategy.yaml`)  
- Telegram alert integration  
- Environment-based configuration  
- Structured logging  

---

## 📦 Requirements

- Python 3.11+
- Git
- Linux / macOS / WSL (Windows via WSL recommended)

---

## ⚙️ Installation

### 1. Clone Repository

```bash
git clone https://github.com/ayusharyaneth/dexy.git
cd dexy
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Upgrade pip (Recommended)

```bash
pip install --upgrade pip
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

---

### 5. Environment Configuration

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` and configure:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- Any additional required keys

If a value exists in both `.env` and `strategy.yaml`, `.env` takes priority.

---

### 6. Strategy Configuration

Edit:

```
strategy.yaml
```

Modify thresholds, filters, or risk parameters according to your trading logic.

---

### 7. Running Dexy

```bash
python3 main.py
```

Dexy will:

- Poll DexScreener  
- Apply strategy filters  
- Send alerts to configured Telegram chat  

---

### 🔄 Updating

```bash
git pull origin main
pip install -r requirements.txt
```

---

## ⚠️ Notes

- Ensure Python 3.11+ is installed  
- Always validate strategy parameters before running in production  
- Never expose your `.env` file publicly  

---
