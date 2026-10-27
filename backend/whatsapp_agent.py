import re
import os
from link_scraper import scrape_job_link
from jd_parser import parse_jd
from rag import match_resumes, get_context
from email_gen import generate_email
from gmail_send import send_email

# In-memory session store for pending WhatsApp applications
# Key: sender WhatsApp number, Value: dict with state & details
pending_applications = {}

HELP_TEXT = """🤖 *Welcome to Job Agent WhatsApp!*

Send me any job post:
• 🔗 *LinkedIn Job or Post Link*
• 📸 *Instagram Hiring Post Link*
• 📝 *Pasted Job Description Text*

How it works:
1. I extract Company, Role, and HR Email
2. I show all your resumes ranked by AI match score
3. You choose which resume to use (or reply AUTO)
4. I draft a tailored email and send it after your YES!
"""


def extract_url(text: str) -> str:
    """Find the first http/https URL in text."""
    match = re.search(r"https?://[^\s]+", text)
    return match.group(0) if match else ""


def build_resume_selection_message(company: str, role: str, hr_email: str, matches: list) -> str:
    """Format the list of resumes as numbered options."""
    lines = [
        "🤖 *Job Agent: Resumes Matched!*",
        "",
        f"🏢 *Company:* {company}",
        f"💼 *Role:* {role}",
        f"📧 *HR Email:* {hr_email}",
        "",
        "📋 *Choose a resume for this application:*"
    ]

    for i, m in enumerate(matches, 1):
        name = m.get("resume", f"Resume {i}")
        score = int(m.get("score", 0))
        reason = m.get("reason", "")
        reason_snippet = f" — _{reason}_" if reason else ""
        lines.append(f"*[ {i} ]* 📄 *{name}* ({score}% match){reason_snippet}")

    lines.extend([
        "",
        "───────────────────────",
        f"👉 Reply with a number (*1* to *{len(matches)}*) to pick that resume",
        "👉 Or reply *AUTO* to use [ 1 ] (top match)",
        "👉 Reply *CANCEL* to discard"
    ])
    return "\n".join(lines)


def build_email_preview_message(app: dict) -> str:
    """Format the generated email draft preview."""
    company = app.get("company")
    role = app.get("role")
    hr_email = app.get("hr_email")
    resume_name = app.get("resume_name")
    subject = app.get("subject")
    body = app.get("body", "")
    preview_body = body[:350] + ("..." if len(body) > 350 else "")

    return (
        f"✉️ *Email Draft Generated with [{resume_name}]!*\n\n"
        f"🏢 *Company:* {company}\n"
        f"💼 *Role:* {role}\n"
        f"📧 *Send To:* {hr_email}\n"
        f"📄 *Attached Resume:* {resume_name}.pdf\n\n"
        f"📌 *Subject:* {subject}\n\n"
        f"📝 *Email Preview:*\n{preview_body}\n\n"
        "───────────────────────\n"
        "👉 Reply *YES* to send this email via Gmail\n"
        "👉 Reply *RESUME* to pick a different resume\n"
        "👉 Reply *CANCEL* to discard"
    )


def generate_email_for_chosen_resume(app: dict, chosen_match: dict) -> str:
    """Generate email for a specific chosen resume and return preview message."""
    resume_name = chosen_match.get("resume", "")
    resume_path = chosen_match.get("path", "")
    jd_text = app["jd_text"]
    company = app["company"]
    role = app["role"]

    resume_context = get_context(resume_name, jd_text)
    email_res = generate_email(
        jd_text=jd_text,
        company=company,
        role=role,
        resume_context=resume_context
    )

    app["state"] = "CONFIRM_SEND"
    app["resume_name"] = resume_name
    app["resume_path"] = resume_path
    app["subject"] = email_res.get("subject", f"Application for {role} at {company}")
    app["body"] = email_res.get("body", "")

    return build_email_preview_message(app)


def handle_whatsapp_message(sender: str, raw_body: str) -> str:
    """Main WhatsApp message handler with resume selection."""
    body = raw_body.strip()
    lower = body.lower()

    # 1. Help
    if lower in ["hi", "hello", "hey", "help", "start", "/start"]:
        return HELP_TEXT

    # 2. Cancel
    if lower in ["cancel", "no", "abort", "discard"]:
        if sender in pending_applications:
            del pending_applications[sender]
            return "❌ Current application has been cancelled. Send another job link whenever you're ready!"
        return "No pending application to cancel. Send a job link or description to get started!"

    # 3. Change resume / back to resume selection
    if lower in ["resume", "resumes", "change", "back"] and sender in pending_applications:
        app = pending_applications[sender]
        app["state"] = "SELECT_RESUME"
        return build_resume_selection_message(
            app["company"], app["role"], app["hr_email"], app["matches"]
        )

    # 4. Handle State: SELECT_RESUME
    if sender in pending_applications and pending_applications[sender].get("state") == "SELECT_RESUME":
        app = pending_applications[sender]
        matches = app.get("matches", [])

        # Check if user sent a number
        chosen_idx = None
        if body.isdigit():
            num = int(body)
            if 1 <= num <= len(matches):
                chosen_idx = num - 1
            else:
                return f"⚠️ Please enter a number between 1 and {len(matches)} (or reply CANCEL)."
        elif lower in ["auto", "1", "best", "top"]:
            chosen_idx = 0

        if chosen_idx is not None:
            chosen = matches[chosen_idx]
            return generate_email_for_chosen_resume(app, chosen)

    # 5. Handle State: CONFIRM_SEND / YES
    if lower in ["yes", "send", "confirm", "send email", "y"]:
        app = pending_applications.get(sender)
        if not app:
            return "⚠️ No pending application found. Please send a job link or description first!"

        # If user replies YES while still at SELECT_RESUME, default to top resume
        if app.get("state") == "SELECT_RESUME":
            chosen = app["matches"][0]
            generate_email_for_chosen_resume(app, chosen)

        to_email = app.get("hr_email", "")
        if not to_email or to_email == "not_found" or "@" not in to_email:
            app["waiting_for_email"] = True
            return (
                "⚠️ *HR Email Not Detected*\n\n"
                f"We couldn't automatically find an HR email for *{app.get('company', 'this role')}*.\n\n"
                "👉 Please reply with the HR email address (e.g. `careers@company.com`) to send it, or reply *CANCEL*."
            )

        # Send via Gmail
        try:
            send_email(
                to=to_email,
                subject=app["subject"],
                body=app["body"],
                resume_path=app["resume_path"]
            )
            resume_file = os.path.basename(app["resume_path"])
            company = app.get("company")
            role = app.get("role")
            del pending_applications[sender]
            return (
                "🎉 *Application Sent Successfully!*\n\n"
                f"🏢 *Company:* {company}\n"
                f"💼 *Role:* {role}\n"
                f"📧 *Sent To:* {to_email}\n"
                f"📎 *Attached Resume:* {resume_file}\n\n"
                "You can verify the outgoing email in your Gmail Sent folder."
            )
        except Exception as e:
            return f"❌ Failed to send email via Gmail: {str(e)}"

    # 6. Waiting for HR Email
    if sender in pending_applications and pending_applications[sender].get("waiting_for_email"):
        email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", body)
        if email_match:
            hr_email = email_match.group(0)
            app = pending_applications[sender]
            app["hr_email"] = hr_email
            app["waiting_for_email"] = False

            try:
                send_email(
                    to=hr_email,
                    subject=app["subject"],
                    body=app["body"],
                    resume_path=app["resume_path"]
                )
                resume_file = os.path.basename(app["resume_path"])
                del pending_applications[sender]
                return (
                    "🎉 *Application Sent Successfully!*\n\n"
                    f"🏢 *Company:* {app.get('company')}\n"
                    f"💼 *Role:* {app.get('role')}\n"
                    f"📧 *Sent To:* {hr_email}\n"
                    f"📎 *Attached Resume:* {resume_file}"
                )
            except Exception as e:
                return f"❌ Failed to send email: {str(e)}"
        else:
            return "⚠️ That doesn't look like a valid email. Please reply with an email address (e.g. hr@company.com) or reply *CANCEL*."

    # 7. New Job Post: Link or Text
    url = extract_url(body)
    try:
        if url:
            jd_text = scrape_job_link(url)
        else:
            jd_text = body

        if len(jd_text.strip()) < 30:
            return "⚠️ The provided job text is too short. Please send a valid job link or paste the full job description."

        parsed = parse_jd(jd_text)
        hr_email = parsed.get("hr_email", "not_found")
        company = parsed.get("company", "not_found")
        role = parsed.get("role", "not_found")

        matches = match_resumes(jd_text)
        if not matches:
            return "⚠️ No resumes found in your `backend/resumes/` folder. Please add at least one resume PDF."

        # Save session in SELECT_RESUME state
        pending_applications[sender] = {
            "state": "SELECT_RESUME",
            "company": company,
            "role": role,
            "hr_email": hr_email,
            "jd_text": jd_text,
            "matches": matches,
            "waiting_for_email": False
        }

        # Present the ranked resume options to the user
        return build_resume_selection_message(company, role, hr_email, matches)

    except Exception as e:
        return f"⚠️ Error processing job posting: {str(e)}"
