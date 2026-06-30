COMMON_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "into",
    "that",
    "this",
    "user",
    "users",
    "ticket",
    "tickets",
    "train",
    "route",
    "page",
}

FILENAME_STOPWORDS = COMMON_STOPWORDS | {
    "then",
    "point",
}

BRIEF_STOPWORDS = FILENAME_STOPWORDS | {
    "success",
    "criteria",
    "preconditions",
    "authenticated",
    "state",
    "role",
    "admin",
    "traveler",
}

COVERAGE_STOPWORDS = COMMON_STOPWORDS | {
    "after",
    "before",
    "button",
    "form",
    "booking",
    "book",
    "clicked",
    "click",
    "waited",
    "verified",
    "verify",
    "opened",
    "open",
}

CONCEPT_ALIASES = {
    "book": ["booking", "reserve", "reservation", "purchase"],
    "booking": ["book", "reserve", "reservation", "purchase"],
    "login": ["authenticate", "authentication", "signin", "session"],
    "logout": ["signout", "session"],
    "pay": ["payment", "checkout", "purchase"],
    "payment": ["pay", "checkout", "purchase"],
    "cancel": ["refund", "revoke", "void"],
    "rebook": ["change", "modify", "exchange"],
    "order": ["purchase", "reservation", "checkout"],
    "route": ["path", "trip", "travel"],
    "station": ["location", "stop", "terminal"],
    "train": ["trip", "travel", "service"],
    "price": ["fare", "cost", "amount"],
    "schedule": ["trip", "timetable", "departure"],
    "user": ["account", "profile", "identity"],
}
