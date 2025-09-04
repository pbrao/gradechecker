# 📊 Grade Checker

An automated **assignment and grade monitoring system** that logs into a student’s **Home Access Center (HAC)** portal, extracts assignments, analyzes performance with an **AI agent**, and optionally sends daily email reports.

---

## 🚀 Features

- **Automated Website Login & Scraping**  
  Logs into HAC using stored credentials and scrapes assignments and grades.

- **Assignment Storage**  
  Saves extracted assignments into `assignments.txt` with a timestamp.

- **AI-Powered Analysis**  
  Uses [pydantic-ai](https://github.com/pydantic/pydantic-ai) with the `gemini-2.0-flash-thinking-exp-01-21` model to:

  - Detect missing assignments (`M - Missing` or `0.00`)
  - Highlight assignments under 80%
  - Summarize overall course grades (below/above 80%)
  - Produce a **mobile-friendly HTML report**

- **Email Delivery**  
  Sends the AI-generated HTML report to multiple recipients via Gmail SMTP.

- **Scheduler**  
  Runs daily at **3:00 PM** to automate the full pipeline (login → scrape → analyze → email).

- **CLI Options**
  ```bash
  python pydanticai_gradechecker.py [OPTIONS]
  ```
  - `--local` → Use local `assignments.txt` (skip scraping)
  - `--email` → Send HTML report via email
  - `--schedule` → Run daily at 3:00 PM

---

## ⚙️ Installation

1. **Clone this repository:**

   ```bash
   git clone https://github.com/<your-username>/grade_checker.git
   cd grade_checker
   ```

2. **Install dependencies:**

   ```bash
   pip install -r docker_upload/requirements.txt
   ```

3. **Set up environment variables in `.env`:**

   ```ini
   HAC_URL=https://hac.schooldistrict.org/HomeAccess
   HAC_USERNAME=your_username
   HAC_PASSWORD=your_password

   GMAIL_SENDER=your_email@gmail.com
   GMAIL_APP_PASSWORD=your_gmail_app_password
   GMAIL_RECEIVERS=recipient1@example.com,recipient2@example.com
   ```

---

## ▶️ Usage

### Run Once (Scraping + Analysis):

```bash
python pydanticai_gradechecker.py
```

### Run with Local File (skip scrape):

```bash
python pydanticai_gradechecker.py --local
```

### Send Results via Email:

```bash
python pydanticai_gradechecker.py --email
```

### Schedule Daily at 3:00 PM:

```bash
python pydanticai_gradechecker.py --schedule
```

---

## 📧 Email Reports

- HTML format with headings, bullet points, and tables
- Mobile-friendly layout
- Includes:
  - Missing assignments table
  - Assignments below 80%
  - Course grades grouped into below and above 80%

---

## 🛠 Project Structure

- `pydanticai_gradechecker.py` → Main application script
- `assignments.txt` → Stores scraped assignments with timestamp
- `docker_upload/` → Docker/WSGI deployment configuration
- `.env.example` → Environment variable template

---

## 📌 Future Improvements

- Add error handling for captcha/log-in failures
- Support alternate email providers
- Provide JSON export option alongside HTML reports

---

## 📝 License

This project is licensed under the MIT License. See [LICENSE](LICENSE) file for details.
