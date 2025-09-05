import click as click_cli
import sys
import smtplib
import time
import schedule as scheduler
import time as schedule_time  # Rename to avoid conflict with existing time import
from email.mime.text import MIMEText
from helium import S, start_chrome, wait_until, write, click as helium_click, Link, kill_browser, get_driver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
from dotenv import load_dotenv
import os
import re
from pydantic_ai import Agent
import logfire


# Load environment variables from .env file
load_dotenv()

# Centralize path for sensitive runtime artifacts
ASSIGNMENTS_PATH = os.getenv('ASSIGNMENTS_PATH', '/tmp/assignments.txt')

# Redact sensitive content from logs by default
SAFE_LOGS = os.getenv('SAFE_LOGS', 'true').lower() in ('1', 'true', 'yes')

# Enable HTML/screenshot snapshots for scraping debug
DEBUG_SNAPSHOTS = os.getenv('DEBUG_SNAPSHOTS', 'false').lower() in ('1', 'true', 'yes')

# Allow disabling Logfire explicitly to isolate scraping issues
LOGFIRE_DISABLE = os.getenv('LOGFIRE_DISABLE', 'false').lower() in ('1', 'true', 'yes')

# Add logfire logging with explicit token configuration for containers/Cloud Run
LOGFIRE_ENABLED = False
try:
    lf_token = os.getenv("LOGFIRE_TOKEN")
    lf_base_url = os.getenv("LOGFIRE_BASE_URL")  # optional, e.g. https://logfire-us.pydantic.dev
    lf_service = os.getenv("LOGFIRE_SERVICE_NAME", "grade-checker")
    lf_version = os.getenv("LOGFIRE_SERVICE_VERSION", "0.1.0")
    lf_env = os.getenv("ENVIRONMENT", "production")

    if LOGFIRE_DISABLE:
        print("LOGFIRE_DISABLE is set; skipping Logfire configuration.")
    elif lf_token:
        # Configure with token (no interactive auth in containers)
        if lf_base_url:
            # Use AdvancedOptions to set base_url (avoids deprecation warning)
            logfire.configure(
                token=lf_token,
                service_name=lf_service,
                service_version=lf_version,
                environment=lf_env,
                advanced=logfire.AdvancedOptions(base_url=lf_base_url),
            )
        else:
            logfire.configure(
                token=lf_token,
                service_name=lf_service,
                service_version=lf_version,
                environment=lf_env,
            )
        LOGFIRE_ENABLED = True
        print("Logfire configured via LOGFIRE_TOKEN")
        print(f"Logfire base: {lf_base_url or 'default'} | service={lf_service} env={lf_env}")
    else:
        print("LOGFIRE_TOKEN not set; Logfire logging disabled for this run.")
except Exception as e:
    print(f"Warning: Logfire configuration failed: {e}")
    print("Continuing without Logfire logging...")
    LOGFIRE_ENABLED = False


def _debug_dump(driver, name: str):
    """Dump a screenshot and DOM snapshot to /tmp when DEBUG_SNAPSHOTS is true."""
    if not DEBUG_SNAPSHOTS:
        return
    try:
        ts = int(time.time())
        base = f"/tmp/hac_{ts}_{name}"
        # Attempt to increase viewport before screenshot
        try:
            driver.set_window_size(1280, 1800)
        except Exception:
            pass
        try:
            driver.save_screenshot(f"{base}.png")
            print(f"[DEBUG] Saved screenshot: {base}.png")
        except Exception as e:
            print(f"[DEBUG] Screenshot failed: {e}")
        try:
            html = driver.page_source
            with open(f"{base}.html", "w", encoding="utf-8") as f:
                f.write(html)
            print(f"[DEBUG] Saved HTML snapshot: {base}.html")
        except Exception as e:
            print(f"[DEBUG] HTML snapshot failed: {e}")
    except Exception as e:
        print(f"[DEBUG] debug_dump error: {e}")

def save_assignments_to_file(content):
    path = ASSIGNMENTS_PATH
    if LOGFIRE_ENABLED:
        with logfire.span("save_assignments_to_file"):
            logfire.info("Saving assignments to file", path=path)
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(path, 'w', encoding='utf-8') as f:
                f.write(f"Timestamp: {timestamp}\n\n")
                for line in content:
                    f.write(line + "\n")
            try:
                os.chmod(path, 0o600)
            except Exception:
                pass
            logfire.info("Assignments saved to file", path=path)
    else:
        print(f"Saving assignments to file at {path}")
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(path, 'w', encoding='utf-8') as f:
            f.write(f"Timestamp: {timestamp}\n\n")
            for line in content:
                f.write(line + "\n")
        try:
            os.chmod(path, 0o600)
        except Exception:
            pass
        print(f"Assignments saved to file at {path}")

def extract_assignments():
    if LOGFIRE_ENABLED:
        with logfire.span("extract_assignments"):
            logfire.info("Extracting assignments from website")
            return _do_extract_assignments()
    else:
        print("Extracting assignments from website")
        return _do_extract_assignments()

def _do_extract_assignments():
    import time
    driver = get_driver()
    
    # Wait for page to fully load
    time.sleep(2)
    wait = WebDriverWait(driver, 30)
    
    # Try multiple selectors and extraction methods
    assignments = []

    # Method 0: Structured parse of HAC "AssignmentClass" blocks and rows
    try:
        # Wait for at least one AssignmentClass section to render
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.AssignmentClass")))
        sections = driver.find_elements(By.CSS_SELECTOR, "div.AssignmentClass")
        structured = []
        for idx, sec in enumerate(sections):
            # Course header is inside .sg-header .sg-header-heading
            course = ""
            try:
                course = sec.find_element(By.CSS_SELECTOR, ".sg-header .sg-header-heading").text.strip()
            except Exception:
                pass

            # Extract Cycle Average (class grade) displayed on the right side of the course header
            class_grade = ""
            try:
                cg_text = ""

                # 0) Direct lookup by index-based IDs (most reliable across variants)
                try:
                    # misspelled variant from HAC
                    header_id = f"plnMain_rptAssigmnetsByCourse_lblHdrAverage_{idx}"
                    cg_text = (driver.find_element(By.ID, header_id).text or "").strip()
                except Exception:
                    try:
                        # corrected variant
                        header_id = f"plnMain_rptAssignmentsByCourse_lblHdrAverage_{idx}"
                        cg_text = (driver.find_element(By.ID, header_id).text or "").strip()
                    except Exception:
                        cg_text = ""

                # 0b) Overall average by index-based IDs
                if not cg_text:
                    try:
                        overall_id = f"plnMain_rptAssigmnetsByCourse_lblOverallAverage_{idx}"
                        txt = (driver.find_element(By.ID, overall_id).text or "").strip()
                        if txt:
                            cg_text = txt if "%" in txt else f"{txt}%"
                    except Exception:
                        try:
                            overall_id = f"plnMain_rptAssignmentsByCourse_lblOverallAverage_{idx}"
                            txt = (driver.find_element(By.ID, overall_id).text or "").strip()
                            if txt:
                                cg_text = txt if "%" in txt else f"{txt}%"
                        except Exception:
                            pass

                # 1) Specific id prefixes (both misspelled and correct variants) within this section
                if not cg_text:
                    id_xpaths = [
                        ".//span[starts-with(@id,'plnMain_rptAssigmnetsByCourse_lblHdrAverage_')]",
                        ".//span[starts-with(@id,'plnMain_rptAssignmentsByCourse_lblHdrAverage_')]",
                    ]
                    for xp in id_xpaths:
                        try:
                            avg_el = sec.find_element(By.XPATH, xp)
                            cg_text = (avg_el.text or "").strip()
                            if cg_text:
                                break
                        except Exception:
                            continue

                # 1b) Broader contains() fallback for header average ids
                if not cg_text:
                    contains_xpaths = [
                        ".//span[contains(@id,'lblHdrAverage')]",
                    ]
                    for xp in contains_xpaths:
                        try:
                            avg_el = sec.find_element(By.XPATH, xp)
                            cg_text = (avg_el.text or "").strip()
                            if cg_text:
                                break
                        except Exception:
                            continue

                # 2) Right-aligned header span within this course header
                if not cg_text:
                    try:
                        avg_el = sec.find_element(
                            By.XPATH,
                            ".//div[contains(@class,'sg-header')]//span[contains(@class,'sg-header-heading') and contains(@class,'sg-right')]"
                        )
                        cg_text = (avg_el.text or "").strip()
                    except Exception:
                        pass

                # 3) Overall average from summary block (again support both variants)
                if not cg_text:
                    overall_xpaths = [
                        ".//span[starts-with(@id,'plnMain_rptAssigmnetsByCourse_lblOverallAverage_')]",
                        ".//span[starts-with(@id,'plnMain_rptAssignmentsByCourse_lblOverallAverage_')]",
                        ".//span[contains(@id,'lblOverallAverage')]",
                    ]
                    for xp in overall_xpaths:
                        try:
                            overall_el = sec.find_element(By.XPATH, xp)
                            txt = (overall_el.text or "").strip()
                            if txt:
                                cg_text = txt if "%" in txt else f"{txt}%"
                                break
                        except Exception:
                            continue

                # 3c) Fallback: any span under header containing visible 'Cycle Average'
                if not cg_text:
                    try:
                        avg_el = sec.find_element(By.XPATH, ".//div[contains(@class,'sg-header')]//span[contains(.,'Cycle') and contains(.,'Average')]")
                        cg_text = (avg_el.text or "").strip()
                    except Exception:
                        pass

                # 4) Last resort: read the entire header text of this section
                if not cg_text:
                    try:
                        header_el = sec.find_element(By.CSS_SELECTOR, ".sg-header")
                        cg_text = (header_el.text or "").strip()
                    except Exception:
                        cg_text = ""

                # Prefer explicit "Cycle/Class Average NN.NN" with optional %, else first explicit percentage, else pure number when text is short
                m = re.search(r'(?:Cycle|Class)\s+Average\s*:?\s*([0-9]{1,3}(?:\.[0-9]{1,2})?)\s*%?', cg_text, re.I)
                if not m:
                    m = re.search(r'([0-9]{1,3}(?:\.[0-9]{1,2})?)\s*%', cg_text)
                if not m:
                    # Handle spans that contain only the numeric value (no percent symbol)
                    m = re.search(r'^\s*([0-9]{1,3}(?:\.[0-9]{1,2})?)\s*%?\s*$', cg_text)
                if m:
                    class_grade = f"{m.group(1)}%"
            except Exception:
                pass

            # Emit a header line for the course with its class grade so it's always captured
            if course and class_grade:
                structured.append(f"Course: {course} | Class Grade: {class_grade}")

            # (dedup) Removed duplicate header emission

            # Rows are in tables with class sg-asp-table and row class sg-asp-table-data-row
            rows = sec.find_elements(By.CSS_SELECTOR, "table.sg-asp-table tr.sg-asp-table-data-row")
            for row in rows:
                tds = row.find_elements(By.TAG_NAME, "td")
                if not tds or len(tds) < 3:
                    continue
                date_due = (tds[0].text or "").strip()
                # assignment is the 3rd column; grab anchor text if present
                assign_cell = tds[2]
                assignment = ""
                try:
                    assignment = assign_cell.find_element(By.TAG_NAME, "a").text.strip()
                except Exception:
                    assignment = (assign_cell.text or "").strip()
                category = (tds[3].text or "").strip() if len(tds) > 3 else ""
                score = (tds[4].text or "").strip() if len(tds) > 4 else ""
                percent = (tds[-1].text or "").strip() if tds else ""
                # Build a compact line suitable for LLM prompt
                parts = []
                if course: parts.append(f"Course: {course}")
                if class_grade: parts.append(f"Class Grade: {class_grade}")
                if assignment: parts.append(f"Assignment: {assignment}")
                if date_due: parts.append(f"Due: {date_due}")
                if category: parts.append(f"Category: {category}")
                if score: parts.append(f"Score: {score}")
                if percent: parts.append(f"Percent: {percent}")
                line = " | ".join(parts)
                if line:
                    structured.append(line)
        if structured:
            print(f"Method structured/AssignmentClass: Found {len(structured)}")
            return structured
    except Exception as e:
        print(f"Structured parse failed: {e}")

    # Preferred: wait then read the primary selector
    try:
        elements = wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, "AssignmentClass")))
        if elements:
            assignments = [e.text for e in elements if e.text and e.text.strip()]
            if assignments:
                print(f"Method wait/AssignmentClass: Found {len(assignments)}")
                return assignments
    except Exception as e:
        print(f"Primary wait for AssignmentClass failed: {e}")
    
    # Method 1: Original selector
    try:
        elements = driver.find_elements(By.CLASS_NAME, "AssignmentClass")
        if elements:
            assignments = [element.text for element in elements if element.text.strip()]
            print(f"Method 1: Found {len(assignments)} assignments with AssignmentClass")
            if assignments:
                return assignments
    except Exception as e:
        print(f"Method 1 failed: {e}")
    
    # Method 2: Try different selectors
    selectors_to_try = [
        ("class", "sg-asp-table-data-row"),
        ("tag", "tr"),
        ("class", "sg-content-grid"),
        ("xpath", "//table//tr[contains(@class, 'sg-asp-table')]"),
        ("xpath", "//div[contains(@class, 'sg-content')]//tr"),
    ]
    
    for method, selector in selectors_to_try:
        try:
            if method == "class":
                elements = driver.find_elements(By.CLASS_NAME, selector)
            elif method == "tag":
                elements = driver.find_elements(By.TAG_NAME, selector)
            elif method == "xpath":
                elements = driver.find_elements(By.XPATH, selector)
            
            if elements:
                temp_assignments = [elem.text for elem in elements if elem.text.strip() and len(elem.text.strip()) > 10]
                if temp_assignments:
                    print(f"Method {method}/{selector}: Found {len(temp_assignments)} assignments")
                    assignments.extend(temp_assignments)
                    break
        except Exception as e:
            print(f"Method {method}/{selector} failed: {e}")
    
    # HAC homepage fallback: extract common markers when iframe/structured selectors fail
    # Looks for:
    #   - a#average.sg-font-larger-average (overall class grade anchors)
    #   - a#courseAssignmentDescription or anchors with OpenAssignmentDialog (assignment titles)
    if not assignments:
        try:
            structured = []
            # Collect overall class averages shown on the Classes dashboard
            avg_elems = driver.find_elements(
                By.CSS_SELECTOR,
                "a#average.sg-font-larger-average, a.sg-font-larger-average#average"
            )
            for el in avg_elems:
                txt = (el.text or "").strip()
                if txt:
                    if "%" not in txt:
                        txt = f"{txt}%"
                    structured.append(f"Class Grade: {txt}")

            # Collect assignment titles shown on the dashboard cards
            title_elems = driver.find_elements(
                By.CSS_SELECTOR,
                "a#courseAssignmentDescription, a[onclick*='OpenAssignmentDialog']"
            )
            for el in title_elems:
                title = (el.text or "").strip()
                if title:
                    structured.append(f"Assignment: {title}")

            if structured:
                print(f"Homepage fallback: Found {len(structured)} items")
                return structured
        except Exception as e:
            print(f"Homepage fallback failed: {e}")

    # Method 3: Extract entire page content if selectors fail
    if not assignments:
        try:
            page_content = driver.find_element(By.TAG_NAME, "body").text
            lines = [line.strip() for line in page_content.split('\n') if line.strip()]
            # Filter for lines that look like assignments (contain grades, dates, etc.)
            assignment_lines = []
            for line in lines:
                if any(keyword in line.lower() for keyword in ['grade', 'assignment', 'test', 'quiz', 'homework', 'project', '%', 'missing']):
                    assignment_lines.append(line)
            
            if assignment_lines:
                print(f"Method 3: Extracted {len(assignment_lines)} assignment lines from page content")
                assignments = assignment_lines
        except Exception as e:
            print(f"Method 3 failed: {e}")
        
    print(f"Final extraction result: {len(assignments)} assignments")
    if LOGFIRE_ENABLED:
        logfire.info(f"Extracted {len(assignments)} assignments")
    else:
        print(f"Extracted {len(assignments)} assignments")
    
    return assignments

def get_credentials():
    if LOGFIRE_ENABLED:
        with logfire.span("get_credentials"):
            logfire.info("Getting credentials from environment variables")
            credentials = {
                "url": os.getenv('HAC_URL'),
                "username": os.getenv('HAC_USERNAME'),
                "password": os.getenv('HAC_PASSWORD')
            }
            logfire.info("Credentials retrieved")
            return credentials
    else:
        print("Getting credentials from environment variables")
        credentials = {
            "url": os.getenv('HAC_URL'),
            "username": os.getenv('HAC_USERNAME'),
            "password": os.getenv('HAC_PASSWORD')
        }
        print("Credentials retrieved")
        return credentials


def login_to_website(url, username, password):
    if LOGFIRE_ENABLED:
        with logfire.span("login_to_website"):
            logfire.info(f"Logging in to website: {url}")
    else:
        print(f"Logging in to website: {url}")
        
    # Google Cloud Run optimized browser startup
    import tempfile
    import atexit
    import subprocess
    import uuid
    import time
    
    # Clean up any existing browser processes
    try:
        subprocess.run(['pkill', '-f', 'chrome'], check=False, capture_output=True)
        subprocess.run(['pkill', '-f', 'chromium'], check=False, capture_output=True)
    except:
        pass
    
    # Create unique temp directory with better permissions
    unique_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
    temp_dir = f'/tmp/chrome-profiles/profile-{unique_id}'
    os.makedirs(temp_dir, exist_ok=True)
    
    # Ensure cleanup
    atexit.register(lambda: __import__('shutil').rmtree(temp_dir, ignore_errors=True))
    
    # Google Cloud Run optimized Chrome options
    chrome_options = [
        '--headless=new',  # Use new headless mode
        '--no-sandbox',
        '--disable-gpu',
        '--disable-software-rasterizer',
        '--disable-background-timer-throttling',
        '--disable-backgrounding-occluded-windows',
        '--disable-renderer-backgrounding',
        '--disable-features=VizDisplayCompositor,TranslateUI',
        '--disable-ipc-flooding-protection',
        '--disable-extensions',
        '--disable-default-apps',
        '--disable-sync',
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-background-networking',
        '--disable-background-timer-throttling',
        '--disable-client-side-phishing-detection',
        '--disable-default-apps',
        '--disable-hang-monitor',
        '--disable-popup-blocking',
        '--disable-prompt-on-repost',
        '--disable-translate',
        '--metrics-recording-only',
        '--safebrowsing-disable-auto-update',
        '--enable-automation',
        '--password-store=basic',
        '--use-mock-keychain',
        '--no-zygote',
        '--window-size=1280,1800',
        f'--user-data-dir={temp_dir}',
        '--remote-debugging-port=0'
    ]
    # Prefer /dev/shm when available; only disable it if explicitly requested
    if os.getenv('DISABLE_DEV_SHM_USAGE', 'false').lower() in ('1', 'true', 'yes'):
        chrome_options.append('--disable-dev-shm-usage')
    
    # Set Chrome options for helium/selenium
    os.environ['CHROME_OPTIONS'] = ' '.join(chrome_options)
    
    # Ensure we're using the correct Chrome binary
    os.environ['CHROME_BIN'] = '/usr/bin/google-chrome'
    
    start_chrome(url, headless=True)
    
    try:
        # Wait for page to load
        wait_until(S("body").exists)

        driver = get_driver()
        _debug_dump(driver, "login_page")
        
        # Robust login using Selenium (multiple selector candidates)
        driver = get_driver()
        login_wait = WebDriverWait(driver, 30)

        username_selectors = [
            (By.ID, "LogOnDetails_UserName"),
            (By.NAME, "LogOnDetails.UserName"),
            (By.CSS_SELECTOR, "input[name='LogOnDetails.UserName']"),
            (By.CSS_SELECTOR, "input#username"),
            (By.XPATH, "//input[@type='text' and (contains(@name,'User') or contains(@id,'User'))]"),
        ]
        password_selectors = [
            (By.ID, "LogOnDetails_Password"),
            (By.NAME, "LogOnDetails.Password"),
            (By.CSS_SELECTOR, "input[name='LogOnDetails.Password']"),
            (By.CSS_SELECTOR, "input#password"),
            (By.XPATH, "//input[@type='password']"),
        ]
        submit_selectors = [
            (By.ID, "login"),
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.XPATH, "//button[contains(.,'Sign In') or contains(.,'Log') or @type='submit']"),
            (By.XPATH, "//input[@type='submit']"),
        ]

        def _find_first(selectors):
            for by, sel in selectors:
                try:
                    el = login_wait.until(EC.presence_of_element_located((by, sel)))
                    if el:
                        return el
                except Exception:
                    continue
            raise Exception("Login element not found for selectors")

        try:
            uel = _find_first(username_selectors)
            pel = _find_first(password_selectors)
            # Clear then type
            uel.clear(); uel.send_keys(username)
            pel.clear(); pel.send_keys(password)
            # Try pressing Enter first
            pel.send_keys(Keys.ENTER)
            time.sleep(1.5)
        except Exception:
            # Fallback to Helium label-based entry if Selenium approach fails
            write(username, into="User Name")
            write(password, into="Password")
        _debug_dump(driver, "after_credentials")

        # Ensure we click a submit control if still on login
        try:
            login_wait.until(lambda d: "classes" in d.page_source.lower() or "home access" not in d.title.lower())
        except Exception:
            try:
                sub = _find_first(submit_selectors)
                sub.click()
            except Exception:
                # Fallback: try Helium click
                helium_click("Sign In")
        _debug_dump(driver, "after_submit")
        
        # Wait for login to complete
        wait_until(Link("Classes").exists)
        helium_click("Classes")
        
        # Wait for legacy iframe to load (id or class)
        wait_until(lambda: S("#sg-legacy-iframe").exists or S(".sg-legacy-iframe").exists)
        
        # Switch into content iframes with retries (different deployments vary)
        driver = get_driver()

        def _switch_into_content_iframe(drv) -> bool:
            # Try known id first
            try:
                iframe = None
                try:
                    iframe = drv.find_element(By.ID, "sg-legacy-iframe")
                except Exception:
                    try:
                        iframe = drv.find_element(By.CSS_SELECTOR, ".sg-legacy-iframe")
                    except Exception:
                        iframe = None
                if iframe is not None:
                    drv.switch_to.frame(iframe)
                    time.sleep(1.0)
                else:
                    raise Exception("Legacy iframe not found by id or class")
            except Exception:
                # Try any iframe that looks like sg content
                iframes = drv.find_elements(By.TAG_NAME, "iframe")
                if not iframes:
                    return False
                switched_any = False
                for f in iframes:
                    try:
                        src = (f.get_attribute("src") or "").lower()
                        id_attr = (f.get_attribute("id") or "").lower()
                        name_attr = (f.get_attribute("name") or "").lower()
                        if any(k in src for k in ["class", "assign", "hac", "student", "grade"]) or \
                           any(k in id_attr for k in ["sg", "legacy", "content"]) or \
                           any(k in name_attr for k in ["sg", "legacy", "content"]):
                            drv.switch_to.frame(f)
                            switched_any = True
                            break
                    except Exception:
                        continue
                if not switched_any:
                    # As last resort, try first iframe
                    try:
                        drv.switch_to.frame(iframes[0])
                        switched_any = True
                    except Exception:
                        return False

            # Optional nested iframe switch
            try:
                inner_iframes = drv.find_elements(By.TAG_NAME, "iframe")
                for f in inner_iframes:
                    src = (f.get_attribute("src") or "").lower()
                    id_attr = (f.get_attribute("id") or "").lower()
                    if any(k in src for k in ["class", "assign"]) or any(k in id_attr for k in ["content"]):
                        drv.switch_to.frame(f)
                        break
            except Exception:
                pass
            return True

        switched_ok = False
        for _ in range(3):
            driver.switch_to.default_content()
            time.sleep(0.5)
            if _switch_into_content_iframe(driver):
                switched_ok = True
                break
            time.sleep(1.0)

        # Try to navigate to the Classwork/Assignments view inside iframe
        try:
            # Click "Classwork" or "Assignments" tab/link if present
            candidates = [
                (By.LINK_TEXT, "Classwork"),
                (By.PARTIAL_LINK_TEXT, "Classwork"),
                (By.LINK_TEXT, "Assignments"),
                (By.PARTIAL_LINK_TEXT, "Assign"),
                (By.XPATH, "//a[contains(.,'Classwork') or contains(.,'Assign')]"),
                (By.XPATH, "//button[contains(.,'Classwork') or contains(.,'Assign')]"),
            ]
            for by, sel in candidates:
                try:
                    el = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((by, sel)))
                    ActionChains(driver).move_to_element(el).pause(0.1).click(el).perform()
                    time.sleep(1.0)
                    break
                except Exception:
                    continue
        except Exception:
            pass
        
        # Proactively wait for common assignment row selectors, with broader set and longer timeouts
        try:
            WebDriverWait(driver, 30).until(
                EC.presence_of_any_elements_located((By.CLASS_NAME, "AssignmentClass"))
            )
        except Exception:
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_any_elements_located((By.XPATH, "//tr[contains(@class,'sg-asp-table') or contains(@class,'sg-asp-table-data-row')]"))
                )
            except Exception:
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_any_elements_located((By.XPATH, "//table//tr"))
                    )
                except Exception:
                    pass  # fall through to extraction fallback

        # Small scroll to ensure rows render
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.5)
            driver.execute_script("window.scrollTo(0, 0);")
        except Exception:
            pass
        
        # Extract and save assignments
        assignments = extract_assignments()
        
        # Strict failure if 0
        if len(assignments) == 0:
            error_msg = "Web scraping failed: Extracted 0 assignments from website (frame/content not found)."
            if LOGFIRE_ENABLED:
                logfire.error(error_msg)
            else:
                print(f"ERROR: {error_msg}")
            raise Exception(error_msg)
        
        save_assignments_to_file(assignments)
        if LOGFIRE_ENABLED:
            logfire.info(f"Login and assignment extraction successful - got {len(assignments)} assignments")
        else:
            print(f"Login and assignment extraction successful - got {len(assignments)} assignments")
        
    except Exception as e:
        if LOGFIRE_ENABLED:
            logfire.error(f"Login or assignment extraction failed: {str(e)}")
        else:
            print(f"Login or assignment extraction failed: {str(e)}")
        raise
    finally:
        # Switch back to default content
        get_driver().switch_to.default_content()
        kill_browser()
        if LOGFIRE_ENABLED:
            logfire.info("Cleaning up and killing the browser")
        else:
            print("Cleaning up and killing the browser")


def main():
    if LOGFIRE_ENABLED:
        with logfire.span("main"):
            logfire.info("Starting Website Login CLI")
    else:
        print("Starting Website Login CLI")
        
    credentials = get_credentials()
    
    try:
        login_to_website(**credentials)
        print("Login successful!")
        if LOGFIRE_ENABLED:
            logfire.info("Login successful")
    except Exception as e:
        print(f"Login failed: {str(e)}")
        if LOGFIRE_ENABLED:
            logfire.error(f"Login failed: {str(e)}")

def invoke_llm(assignments_content):
    if LOGFIRE_ENABLED:
        with logfire.span("invoke_llm"):
            logfire.info("Invoking LLM for analysis")
    else:
        print("Invoking LLM for analysis")
    # Clean and format the assignments content
    cleaned_content = "\n".join([
        line.strip() for line in assignments_content.splitlines() 
        if line.strip() and not line.startswith("Timestamp:")
    ])
    
    # Prepare the prompt
    prompt = f"""
    Analyze this student's assignments and grades. Focus on:
    1. Missing assignments (marked with 'M - Missing' or a '0.00')
    2. Class grades below 80%
    3. Class grades above 80%
    
    Here is the data:
    {cleaned_content[:10000]}
    
    Provide the following sections:
    - Summary of Key Issues
        -- Number of missing assignments plus those with a 0.00 grade
        -- Number of class assignment grades that are less than 80%
    - Missing Assignments
        -- Table of all of the missing assignments with formatted spacing to look like a table
        -- Course Name
        -- Assignment
        -- Due Date
        -- Sort by Due Date from the newest date to the oldest date
    - Assignments Below 80%
        -- Table of all of assignments with a grade below 80%
        -- Course Name
        -- Assignment
        -- Due Date
        -- Sort by assignment grade from lowest to highest
    - Low Class Grades (Below 80%) 
        -- Table of overall course grades below 80% with formatted spacing to look like a table
        -- Course Name
        -- Current Grade
        -- Sort by Current Grade from lowest to highest
    - Other Class Grades (Above 80%) 
        -- Table of overall course grade above 80% with formatted spacing to look like a table
        -- Course Name
        -- Current Grade
        -- Sort by Current Grade from lowest to highest
    
    Keep the response concise and focused.
    The response should be in HTML format that includes headings, bullet points, 
    and tables with headings so that it is easy to read.
    Make the HTML so that it displays correctly on a mobile device
    Only include the analysis within the start <html> and end <html> tags.
    """
    system_prompt = """
    You are an expert in evaluating the grades and performance of high school students.
    """
    #agent = Agent('anthropic:claude-3-5-sonnet-latest', system_prompt=system_prompt, model_settings={'temperature': 0.0})
    #agent = Agent('gemini-2.0-flash-thinking-exp-01-21', system_prompt=system_prompt, model_settings={'temperature': 0.0})
    agent = Agent('gemini-2.5-flash', system_prompt=system_prompt, model_settings={'temperature': 0.0})
    try:
        # Run the agent and normalize to a pure HTML string
        result = agent.run_sync(prompt)

        # Prefer the "output" attribute used by recent pydantic-ai AgentRunResult
        if hasattr(result, "output"):
            html = result.output
        # Back-compat fallbacks for other SDK/result shapes
        elif hasattr(result, "data"):
            html = result.data
        elif hasattr(result, "content"):
            html = result.content
        elif hasattr(result, "text"):
            html = result.text
        elif isinstance(result, dict) and "output" in result:
            html = result["output"]
        else:
            # Last resort: stringification
            html = str(result)

        # Ensure it's a string for MIMEText; some SDKs can return non-str types
        if isinstance(html, bytes):
            html = html.decode("utf-8", errors="ignore")
        else:
            html = str(html)

        return html
    except Exception as e:
        return f"Error processing assignments: {str(e)}"

def send_email(analysis):
    if LOGFIRE_ENABLED:
        with logfire.span("send_email"):
            logfire.info("Sending email with analysis")
    else:
        print("Sending email with analysis")
    """Sends the analysis via email with HTML content to multiple recipients."""
    sender_email = os.getenv('GMAIL_SENDER')
    sender_password = os.getenv('GMAIL_APP_PASSWORD')
    receiver_emails = [email.strip() for email in os.getenv('GMAIL_RECEIVERS').split(',')]
    
    # Create subject with current date
    current_date = time.strftime("%m/%d/%Y")
    subject = f"Naina's Grades/Assignments - {current_date}"
    
    # Create message as MIMEText with HTML content
    msg = MIMEText(analysis, 'html')
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = ', '.join(receiver_emails)  # Join all recipients with commas

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            # Send to all recipients
            server.sendmail(
                sender_email,
                receiver_emails,  # Pass list of recipients
                msg.as_string()
            )
            print(f"Email sent successfully to {len(receiver_emails)} recipients!")
            if LOGFIRE_ENABLED:
                logfire.info(f"Email sent successfully to {len(receiver_emails)} recipients!")
    except Exception as e:
        if LOGFIRE_ENABLED:
            logfire.error(f"Error sending email: {e}")
        print(f"Error sending email: {e}")

def scheduled_job():
    if LOGFIRE_ENABLED:
        with logfire.span("scheduled_job"):
            logfire.info("Running scheduled job")
    else:
        print("Running scheduled job")
    """Function to be scheduled to run daily at 3:00 PM"""
    print(f"Running scheduled job at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    try:
        # Get credentials and login
        credentials = get_credentials()
        login_to_website(**credentials)
        
        # Read the saved assignments
        path = ASSIGNMENTS_PATH
        with open(path, 'r') as f:
            assignments_content = f.read()
        
        # Analyze assignments
        analysis = invoke_llm(assignments_content)
        print("\nAnalysis complete!")
        
        # Send email with analysis
        send_email(analysis)
        
        print("Scheduled job completed successfully")
        if LOGFIRE_ENABLED:
            logfire.info("Scheduled job completed successfully")
    except Exception as e:
        if LOGFIRE_ENABLED:
            logfire.error(f"Error in scheduled job: {str(e)}")
        print(f"Error in scheduled job: {str(e)}")

@click_cli.command()
@click_cli.option('--local', is_flag=True, help='Use local assignments.txt instead of scraping website')
@click_cli.option('--email', is_flag=True, help='Send analysis via email')
@click_cli.option('--schedule', is_flag=True, help='Schedule to run daily at 3:00 PM')
def cli(local, email, schedule):
    if LOGFIRE_ENABLED:
        with logfire.span("cli"):
            logfire.info("Starting CLI")
    else:
        print("Starting CLI")
    """Grade Checker Application"""
    if schedule:
        print("Setting up scheduled job to run daily at 3:00 PM...")
        if LOGFIRE_ENABLED:
            logfire.info("Setting up scheduled job to run daily at 3:00 PM...")
        scheduler.every().day.at("15:00").do(scheduled_job)
        #scheduler.every(5).minutes.do(scheduled_job)
        print(f"Job scheduled. Current time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        if LOGFIRE_ENABLED:
            logfire.info(f"Job scheduled. Current time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("Press Ctrl+C to exit")
        
        try:
            while True:
                scheduler.run_pending()
                schedule_time.sleep(60)  # Check every 60 seconds 
        except KeyboardInterrupt:
            print("Scheduler stopped by user")
            if LOGFIRE_ENABLED:
                logfire.info("Scheduler stopped by user")
            sys.exit(0)
    else:
        try:
            print("Starting grade check...")
            if LOGFIRE_ENABLED:
                logfire.info("Starting grade check...")
            
            if not local:
                print("Scraping website for assignments...")
                if LOGFIRE_ENABLED:
                    logfire.info("Scraping website for assignments...")
                credentials = get_credentials()
                login_to_website(**credentials)
                print("Website scraping complete.")
                if LOGFIRE_ENABLED:
                    logfire.info("Website scraping complete.")
            else:
                print("Using local assignments file...")
                if LOGFIRE_ENABLED:
                    logfire.info("Using local assignments file...")
            
            # Read the saved assignments
            print("Reading assignments file...")
            if LOGFIRE_ENABLED:
                logfire.info("Reading assignments file...")
            path = ASSIGNMENTS_PATH
            if local and not os.path.exists(path):
                # For local testing fall back to the sample file baked into the image
                path = 'assignments.txt'
            with open(path, 'r') as f:
                assignments_content = f.read()
            
            print("Sending assignments to LLM for analysis...")
            if LOGFIRE_ENABLED:
                logfire.info("Sending assignments to LLM for analysis...")
            try:
                analysis = invoke_llm(assignments_content)
                print("\nAnalysis complete!")
                # Avoid printing analysis HTML (may contain PII) unless explicitly allowed
                if not SAFE_LOGS:
                    print(analysis)
                if LOGFIRE_ENABLED:
                    logfire.info("Analysis complete!")
                
                if email:
                    print("\nSending analysis via email...")
                    if LOGFIRE_ENABLED:
                        logfire.info("Sending analysis via email...")
                    send_email(analysis)
                
                #sys.exit(0)  # Exit successfully
            except Exception as e:
                print(f"\nError during LLM analysis: {str(e)}")
                if LOGFIRE_ENABLED:
                    logfire.error(f"LLM analysis failed: {str(e)}")
                sys.exit(1)  # Exit with error
            
        except Exception as e:
            print(f"\nError: {str(e)}")
            if LOGFIRE_ENABLED:
                logfire.error(f"Grade check failed: {str(e)}")
            sys.exit(1)  # Exit with error

if __name__ == "__main__":
    if LOGFIRE_ENABLED:
        with logfire.span("grade_checker_application"):
            cli()
    else:
        cli()
