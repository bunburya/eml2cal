import shlex
import smtplib
import ssl
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from email.message import EmailMessage
from typing import Optional, Any

from icalendar import Event

from eml2cal.utils import chained_get


@dataclass
class EmailSummary:
    """A summary of an email that has been processed (or that we tried to process).

    :param date: The "Date" header of the email.
    :param from_header: The "From" header of the email.
    :param subject: The subject of the email.
    """
    date: datetime
    from_header: str
    subject: str

    @staticmethod
    def from_email(email: EmailMessage) -> "EmailSummary":
        return EmailSummary(
            email.get("Date"),
            email.get("From"),
            email.get("Subject")
        )


@dataclass
class EventEmailSummary:
    """A summary of the processing of one email.

    :param email_summary: A summary of the email itself.
    :param num_total_events: The total number of events found.
    :param num_unique_events: The number of unique (by start time and end time) events found.
    """
    email_summary: EmailSummary
    num_total_events: int
    num_unique_events: int

    @staticmethod
    def from_email_and_stats(email: EmailMessage,
                             num_total_events: int,
                             num_unique_events: int) -> "EventEmailSummary":
        return EventEmailSummary(
            EmailSummary.from_email(email),
            num_total_events,
            num_unique_events
        )


@dataclass
class EventSummary:
    """A summary of a calendar event.

    :param start: The start time.
    :param end: The end time.
    :param name: The name ("summary") of the event.
    :param num_conflicts: The number of events with the same start and end time in a calendar."""
    start: Optional[datetime]
    end: Optional[datetime]
    name: str
    num_conflicts: int

    @staticmethod
    def from_event(event: Event, num_conflicts: int) -> "EventSummary":
        dtstart = event.get("dtstart")
        dtend = event.get("dtend")
        return EventSummary(
            dtstart.dt if dtstart else None,
            dtend.dt if dtend else None,
            event.get("summary"),
            num_conflicts
        )


@dataclass
class Summary:
    """A summary of the actions taken during one run of eml2cal.

    :param start_time: The approximate time the script started running.
    :param end_time: The approximate time the script finished.
    :param checked: A list of summaries of all emails checked.
    :param extracted: A list of summaries of all emails that were found to have events.
    :param errors: A list of summaries of emails that could not be processed due to error.
    :param conflicts: A list of summaries of events that were not added to the calendar due to conflicting events.
    """
    start_time: datetime
    checked: list[EmailSummary] = field(default_factory=list)
    extracted: list[EventEmailSummary] = field(default_factory=list)
    errors: list[EmailSummary] = field(default_factory=list)
    conflicts: list[EventSummary] = field(default_factory=list)
    end_time: datetime = None

    def to_text(self) -> str:
        """Output a detailed report as a string."""
        agg_total_events = sum([e.num_total_events for e in self.extracted])
        agg_unique_events = sum([e.num_unique_events for e in self.extracted])
        lines = []
        lines.append("eml2cal summary")
        lines.append("")
        lines.append(f"Running time: {self.start_time} to {self.end_time} ({self.end_time - self.start_time})")
        lines.append("")
        lines.append(f"Checked {len(self.checked)} emails.")
        lines.append(f"Found {agg_total_events} events ({agg_unique_events} unique) in {len(self.extracted)} emails.")
        lines.append(f"Encountered {len(self.errors)} errors when trying to process emails.")
        lines.append(f"{len(self.conflicts)} events not added due to conflicts in calendar.")
        lines.append("")
        lines.append("Event emails:")
        for i, eml in enumerate(self.extracted):
            lines.append(f"  {i}:")
            lines.append(f"    Received: {eml.email_summary.date}")
            lines.append(f"    From: {eml.email_summary.from_header}")
            lines.append(f"    Subject: {eml.email_summary.subject}")
            lines.append(f"    Total events: {eml.num_total_events}")
            lines.append(f"    Unique events: {eml.num_unique_events}")
        lines.append("")
        lines.append("Conflicts:")
        for i, evt in enumerate(self.conflicts):
            lines.append(f"  {i}:")
            lines.append(f"    Time: {evt.start} to {evt.end}")
            lines.append(f"    Name: {evt.name}")
            lines.append(f"    Conflicts: {evt.num_conflicts}")

        return "\n".join(lines)


def send_report(config: dict[str, Any], summary: Summary):
    server = chained_get(config, "report.smtp.server")
    port = chained_get(config, "report.smtp.port")
    uname = chained_get(config, "report.smtp.username")
    passwd_cmd = chained_get(config, "report.smtp.password_cmd")
    to_addr = chained_get(config, "report.smtp.to_address")
    if not (server and uname and passwd_cmd and to_addr):
        raise ValueError("Could not find SMTP authentication details in configuration.")
    from_addr = chained_get(config, "report.smtp.from_address", uname)
    pass_output = subprocess.run(shlex.split(passwd_cmd), capture_output=True)
    if pass_output.returncode:
        raise SystemError(pass_output.stderr.decode())
    passwd = pass_output.stdout.decode().strip()
    msg = EmailMessage()
    msg["To"] = to_addr
    msg["From"] = from_addr
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    msg["Subject"] = f"[eml2cal] Action report: {now}"
    msg.set_content(summary.to_text())
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(server, port, context=context) as server:
        server.login(uname, passwd)
        server.send_message(msg)
