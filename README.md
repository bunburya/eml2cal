# eml2cal

`eml2cal` is a Python script that wraps [kitinerary-extractor](https://apps.kde.org/en-gb/kitinerary-extractor/),
which is a command line tool that uses the KDE [KItinerary](https://invent.kde.org/pim/kitinerary) library to extract
data about events and reservations from emails, PDFs and other documents. kitinerary-extractor is capable of converting
many types of email to calendar events, but eml2cal adds features such as:

* **mailbox integration** Point the script to a mailbox in the [Maildir](https://en.wikipedia.org/wiki/Maildir) or
  [mbox](https://en.wikipedia.org/wiki/Mbox) format to have it process all emails in that mailbox.
* **pre-processing**: Performing actions on emails before they are fed to kitinerary-extractor, such as altering the 
  headers.
* **iCalendar generation**: Creating [iCalendar](https://en.wikipedia.org/wiki/ICalendar) events from emails, with more
  information and more fine-grained control than kitinerary-extractor's own iCalendar output feature.
* **CalDAV integration**: Add created iCalendar events directly to a [CalDAV](https://en.wikipedia.org/wiki/CalDAV)
  calendar.
* **reporting**: Send a report summarising the actions that have been taken, for monitoring purposes.

I developed it for my own personal needs and it hasn't been extensively tested, but hopefully others find it useful.

## Dependencies

eml2cal is written in Python. The Python dependencies are listed in the Pipfile and other than that, the main dependency
is kitinerary-extractor, which can be
[installed via flatpak](https://invent.kde.org/pim/kitinerary/#command-line-extractor).

## Configuration

eml2cal is configured using a TOML file. A valid configuration file must be available: configuration using command-line
options is not currently supported. A commented example TOML file is provided in the repo. You can point eml2cal to your
config file with the `--config` option; otherwise, it will search in your standard user config directory as determined
by the [platformdirs](https://github.com/platformdirs/platformdirs) library (on Linux, probably
`$HOME/.config/eml2cal/`).

## Usage

```commandline
git clone https://github.com/bunburya/eml2cal.git
cd eml2cal
pip install .
eml2cal --config my_config.toml
```