KEYWORDS = {
    "food_and_dining": (
        "restaurant",
        "cafe",
        "coffee",
        "pizza",
        "burger",
        "swiggy",
        "zomato",
        "tea",
    ),
    "groceries": ("grocery", "supermarket", "mart", "fresh", "vegetable"),
    "transport": ("uber", "ola", "taxi", "metro", "fuel", "petrol", "diesel"),
    "utilities": ("electricity", "water", "internet", "mobile", "broadband"),
    "shopping": ("store", "fashion", "amazon", "flipkart", "retail"),
    "health": ("pharmacy", "hospital", "clinic", "medical", "health"),
    "entertainment": ("cinema", "movie", "netflix", "spotify", "game"),
    "travel": ("hotel", "airline", "flight", "railway", "booking"),
    "education": ("school", "college", "course", "book", "tuition"),
}

CATEGORIES = (*KEYWORDS.keys(), "other")


def categorize_expense(
    merchant: str | None,
    document_text: str,
    remembered_category: str | None = None,
) -> str:
    if remembered_category in CATEGORIES:
        return remembered_category
    searchable = f"{merchant or ''} {document_text}".casefold()
    scores = {
        category: sum(keyword in searchable for keyword in keywords)
        for category, keywords in KEYWORDS.items()
    }
    best_category = max(scores, key=scores.get)
    return best_category if scores[best_category] > 0 else "other"
