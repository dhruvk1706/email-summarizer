from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from gmail import _extract_body

# plain-text single-part
plain = MIMEText("hello world", "plain")
assert _extract_body(plain) == "hello world"

# html-only single-part (the bug: used to return raw markup)
html_only = MIMEText("<p>Hi <b>there</b></p>", "html")
assert _extract_body(html_only) == "Hi there"

# multipart with only text/html (the bug: used to return "")
multi_html = MIMEMultipart("alternative")
multi_html.attach(MIMEText("<p>Special <em>offer</em>!</p>", "html"))
assert _extract_body(multi_html) == "Special offer !"

# multipart with both: text/plain preferred
multi_both = MIMEMultipart("alternative")
multi_both.attach(MIMEText("<p>rich</p>", "html"))
multi_both.attach(MIMEText("plain wins", "plain"))
assert _extract_body(multi_both) == "plain wins"

print("all _extract_body checks passed")
