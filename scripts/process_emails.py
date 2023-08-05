import sys
import os
import subprocess
import smtplib
from datetime import datetime
from mailbox import Mailbox, Maildir
from email.message import Message, EmailMessage
from typing import Optional, Collection, Iterable

from icalendar import Calendar, Event, vCalAddress, vText

CMD = ["/usr/bin/flatpak", "run", "org.kde.kitinerary-extractor", "-o", "iCal"]


def has_real_event(cal: Calendar) -> bool:
    for evt in cal.walk("VEVENT"):
        if ("DTSTART" in evt) and ("DTEND" in evt):
            return True
    return False

def add_attendee(cal: Calendar, email_addr: str) -> Calendar:
    """Add `email_addr` as an attendee to each event in `cal`. Modifies `cal`
    in-place.
    """
    for evt in cal.walk("VEVENT"):
        a = vCalAddress(f"MAILTO:{email_addr}")
        a.params["ROLE"] = vText("REQ-PARTICIPANT")
        evt.add("attendee", a, encode=0)
    return cal

def merge_calendars(cals: Collection[Calendar]) -> Calendar:
    """Merge a number of calendars into one, which has the timezone and event
    info from all calendars.
    """
    # Keep track of the timezones we've already added
    added_tzids = set()

    new_cal = Calendar()

    for c in cals:
        for tz in c.walk("VTIMEZONE"):
            tzid = tz["TZID"]
            if tzid not in added_tzids:
                new_cal.add_component(tz)
                added_tzids.add(tzid)
        for evt in c.walk("VEVENT"):
            new_cal.add_component(evt)
    return new_cal


def process_email(email: Message) -> Optional[Calendar]:
    """Process `email`, determining whether it contains a relevant event and
    adding it to `main_cal` if so.
    """
    output = subprocess.run(CMD, input=email.as_bytes(), capture_output=True)
    if output.returncode:
        # kitinerary-extractor returned an error
        return
    cal = Calendar.from_ical(output.stdout.decode())
    if has_real_event(cal):
        return cal

def process_mailbox(
        mb: Mailbox,
        email_addr: Optional[str] = None
    ) -> Optional[tuple[Calendar, list[str]]]:
    """Process each email in `mailbox`, returning a calendar containing all
    parsed events (or None if no events were found). Also return a list of
    details of emails that had events. `email_addr` will be added as an
    attendee to each event.
    """

    cals = []
    emails = []
    for msg in mb:
        c = process_email(msg)
        if c is not None:
            cals.append(c)
            emails.append(" ".join((
                msg.get("Date"),
                msg.get("From"),
                msg.get("Subject")
            )))
    if cals:
        c = merge_calendars(cals)
        if email_addr:
            add_attendee(c, email_addr)
        return c, emails

def get_pass(pass_name: str) -> str:
    """Get password for smtp, using `pass`."""
    cmd = ["/usr/bin/pass", "show", pass_name]
    output = subprocess.run(cmd, capture_output=True)
    return output.stdout.decode().strip()

def email_calendar(
        to: str,
        subject: str,
        event_details: Iterable[str],
        cal: Calendar,
        sender: str,
        passwd: str,
        smtp_server: str,
        smtp_port: int = 587,
    ):
    """Send an email with attachment."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg.set_content('\n'.join(event_details))
    msg.add_attachment(
        cal.to_ical(), 
        maintype="text", 
        subtype="calendar",
        filename="events.ics"
    )
    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(sender, passwd)
        server.send_message(msg)

def main():
    _, mdir, email_addr, pass_name, smtp_server = sys.argv
    mail_addr = sys.argv[2]
    if len(sys.argv) > 3:
        CMD.extend(["--additional-search-path", sys.argv[3]])
    result = process_mailbox(Maildir(mdir), email_addr)
    if result is not None:
        cal, emails = result
        email_calendar(
            email_addr,
            f"Events: {datetime.now()}",
            emails,
            cal,
            email_addr,
            get_pass(pass_name),
            smtp_server
            )
    #    os.makedirs("calendars")
    #    with open("output.ics", "wb") as f:
    #        f.write(cal.to_ical())
    #    with open("emails.txt", "w") as f:
    #        for e in emails:
    #            f.write(f"{e}\n")
    #    print(f"{len(emails)} event emails found.")
    #else:
    #    print(f"0 event emails found.")

def test():
    _, event_detail_file, cal_file, email_addr, pass_name, smtp_server = sys.argv
    with open(event_detail_file) as f:
        event_details = f.readlines()
    with open(cal_file, "rb") as f:
        cal = Calendar.from_ical(f.read())
    email_calendar(
        email_addr,
        "Test email",
        event_details,
        cal,
        email_addr,
        get_pass(pass_name),
        smtp_server
    )

if __name__ == "__main__":
    #test()
    main()

