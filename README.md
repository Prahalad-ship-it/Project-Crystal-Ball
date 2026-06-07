# Crystal Ball: Real-Time Quantitative Analytics and Signal Processing Engine

Crystal Ball is a high-performance, asynchronous full-stack web application designed to track a dynamic watchlist of equities. It ingests real-time market data pipelines, computes technical overlay matrices, and executes deterministic rule-based evaluation vectors to yield instant trading signals (STRONG BUY, BUY, HOLD, SELL, STRONG SELL). 

**The application is fully deployed and hosted as a live, continuous web service on Render.**

---

## Production Deployment

* **Live Cloud Web Service:** https://project-crystal-ball.onrender.com/
* **Local Development Interface:** http://localhost:5000

---

## How the Application Works (System Architecture)

The application is structured as a complete data pipeline and presentation layer built entirely within a unified Python architecture. It operates via four primary interconnected systems:

### 1. Asynchronous Background Data Engine
If a server must download data for multiple assets simultaneously upon a user request, the application will experience severe I/O blocking and latency. To solve this, the architecture utilizes **Python Threading**. 
* An isolated daemon thread (`threading.Thread`) runs a continuous infinite loop in the background.
* Every 60 seconds, it connects to the Yahoo Finance API (`yfinance`) to download 6 months of daily OHLCV (Open, High, Low, Close, Volume) pricing arrays for every asset in the defined watchlist.
* The processed results are immediately injected into a non-blocking in-memory cache layer (`_cache`) for instantaneous, zero-latency retrieval by the web server.

### 2. Algorithmic Processing Core (The "Brain")
Once the raw market matrices are downloaded, the system acts as an automated quantitative analyst. Utilizing `pandas` and `pandas_ta`, it calculates complex technical indicators:
* **Relative Strength Index (RSI-14):** A momentum oscillator mapping overbought and oversold thresholds.
* **Simple Moving Averages (SMA-20 & SMA-50):** Baseline structural support and resistance benchmarks determining the macro-trend.
* **Moving Average Convergence Divergence (MACD):** Measures the secondary derivative histogram to determine trend momentum.
* **Bollinger Bands (%B):** Measures volatility and price variance extremes calculated at 2 standard deviations.

### 3. RESTful Web Server & Cloud Deployment (Render)
The application is deployed on **Render** as a live web service. The deployment architecture utilizes a production-ready Python environment (pinned to Python 3.12 to ensure stable compilation of mathematical dependencies like `numba`).
* A lightweight **Flask** WSGI application serves the frontend routing (`/`).
* A RESTful API endpoint (`/api/signals`) is exposed to the frontend. It serializes the constantly updating in-memory dictionary cache into JSON payloads, delivering sub-millisecond response times.

### 4. Zero-Dependency Graphical Front-End
The layout implements a responsive, dark-mode financial terminal interface engineered for minimal resource consumption.
* **Asynchronous Polling:** A native JavaScript `fetch` mechanism polls the Flask API every 60 seconds, mutating the DOM dynamically without requiring heavy full-page reloads.
* **HTML5 Canvas:** Historical 30-day price trends are painted on the client side programmatically using native HTML5 Canvas drawing mathematics. This dynamically generates scaled gradient sparklines and avoids the heavy overhead of third-party charting libraries like Chart.js.

---

## Technical Skills Demonstrated

This project serves as a comprehensive demonstration of the following software engineering competencies:

* **Cloud Deployment & DevOps (Render):** Successfully deployed the full-stack application as a live web service on Render, managing WSGI server execution, configuring build commands, and handling complex environment dependency resolution in a production setting.
* **Backend Development & API Design:** Structuring RESTful JSON endpoints, handling Flask routing, and managing OS environment variables.
* **Concurrency & Performance Optimization:** Implementing Python multi-threading to detach heavy network requests from the main server thread, and utilizing in-memory data caching for rapid API delivery.
* **Quantitative Finance & Data Science:** Managing time-series data with Pandas/NumPy, translating complex financial formulas into deterministic programmatic rules, and calculating dynamic risk-management parameters (such as ATR-based Stop-Loss targets).
* **Frontend Engineering:** Fetching asynchronous payloads via the JavaScript Fetch API, executing targeted DOM manipulation, and programmatically generating data visualizations using Canvas mathematics.

---

## Technical Stack and Dependencies

* **Core Runtime:** Python 3.12
* **Application Framework:** Flask 
* **Data Orchestration:** Pandas, NumPy
* **Mathematical Analytics Engine:** Pandas-TA 
* **Ingestion Protocol:** Yahoo Finance API (`yfinance`)
* **Cloud Infrastructure:** Render Web Services 
 **Claude Code**  In order to review my coding mistakes and implment and build some fo the code

---

## Rule Engine Logic Specification

The system evaluates incoming mathematical matrices against the following deterministic logic conditions:

* **STRONG BUY:** `RSI < 35` AND `Spot Price > SMA20` AND `MACD Histogram > 0`
* **BUY:** `RSI < 45` AND `Spot Price > SMA20` (or `RSI < 50` AND `Spot Price > SMA20` AND `Spot Price > SMA50`)
* **STRONG SELL:** `RSI > 65` AND `Spot Price < SMA20` AND `MACD Histogram < 0`
* **SELL:** `RSI > 55` AND `Spot Price < SMA20`
* **HOLD:** Evaluated automatically when data vectors fail to intercept the boundary definitions above.

---

## Local Installation and Workspace Configuration

### Prerequisites
* Python 3.10 through Python 3.13 (Note: The structural math engine compiler strictly restricts target deployment parameters to Python < 3.14).

### 1. Repository Acquisition
Clone the source workspace and navigate to the root deployment directory:
```bash
git clone [https://github.com/Prahalad-ship-it/Project-Crystal-Ball.git](https://github.com/Prahalad-ship-it/Project-Crystal-Ball.git)
cd Project-Crystal-Ball

2. Dependency Resolution
Construct a virtual execution environment and install the verified production manifest:

Bash
pip install -r requirements.txt
3. Server Execution
Run the primary execution entry point to start the WSGI listener:

Bash
python realtime_signals.py
Note: The initial operational sequence performs a full initialization process to cache technical indicator matrices across the system watchlist. This requires approximately 30 seconds of computational warm-up time, after which the client web dashboard will be fully accessible at http://localhost:5000.

Compliance and Disclaimer Notice
This system architecture is engineered purely as an educational exercise and portfolio reference module demonstrating asynchronous backend orchestration and cloud deployment. It does not constitute investment advice, financial strategy modeling, or algorithmic asset management recommendations.