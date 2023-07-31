import subprocess
import mailbox

import sys

from icalendar import Calendar, Event

CMD = ["/usr/bin/flatpak", "run", "org.kde.kitinerary-extractor", "-o", "iCal"]

mdir = mailbox.Maildir(sys.argv[1])

def has_real_event(cal: Calendar) -> bool:
    for evt in cal.walk("VEVENT"):
        if ("DTSTART" in evt) and ("DTEND" in evt):
            return True
    return False


for key, msg in mdir.iteritems():
    output = subprocess.run(CMD, input=msg.as_bytes(), capture_output=True)
    if output.returncode:
        continue
    cal = Calendar.from_ical(output.stdout.decode())
    if has_real_event(cal):
        print(f"{key} has real event")

