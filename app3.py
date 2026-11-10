import streamlit as st

# MUST be the very first Streamlit command in the script
st.set_page_config(page_title="Movie Sentiment Analyzer", layout="wide")

import requests
import pickle
import re
from difflib import SequenceMatcher
from nltk.corpus import stopwords
from streamlit_searchbox import st_searchbox

model = pickle.load(open("model.pkl", "rb"))
tfidf = pickle.load(open("tfidf.pkl", "rb"))
stop_words = set(stopwords.words('english'))

# Compatibility patch: the model was trained/pickled with a newer
# scikit-learn version that no longer sets this internal attribute,
# but the older scikit-learn running this app still expects it to
# exist inside predict_proba(). Restoring the default value avoids
# having to retrain the model just because of a version mismatch.
if not hasattr(model, "multi_class"):
    model.multi_class = "auto"

# Prefer Streamlit secrets over hardcoded keys.
# Create a file .streamlit/secrets.toml in your project root with:
#   OMDB_KEY = "your_own_key"
#   TMDB_KEY = "your_own_key"
# Falls back to the old hardcoded keys only if secrets aren't set.
def get_secret(key, default=None):
    try:
        return st.secrets[key]
    except Exception:
        return default


OMDB_KEY = get_secret("OMDB_KEY", "523ebf15")
TMDB_KEY = get_secret("TMDB_KEY", "5daa24d87eeb144ba22e9b9c66d6a7e9")

def clean_text(text):
    text = re.sub(r'<.*?>', '', text)
    text = re.sub(r'[^a-zA-Z\s]', '', text)
    text = text.lower()
    text = text.strip()
    return text


def remove_stopwords(text):
    words = text.split()
    words = [w for w in words if w not in stop_words]
    return " ".join(words)


def similarity(a, b):
    """0-1 score of how similar two strings are (typo-tolerant)."""
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def tmdb_search_raw(query):
    """Hits TMDB's search endpoint and returns the raw list of results (or [])."""
    search_url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_KEY}&query={query}"
    try:
        resp = requests.get(search_url, timeout=10)
    except requests.exceptions.RequestException as e:
        st.error(f"Could not reach TMDB: {e}")
        return []

    if resp.status_code == 401:
        st.error("TMDB API key invalid. Get a free key at https://www.themoviedb.org/settings/api")
        return []
    if resp.status_code == 429:
        st.error("TMDB rate limit hit — this key is being used by too many requests right now. "
                  "Get your own free API key or wait a bit and retry.")
        return []
    if resp.status_code != 200:
        st.error(f"TMDB search returned an error (status {resp.status_code}).")
        return []

    results = resp.json().get("results", [])
    return results


def tmdb_get_imdb_id(tmdb_id):
    """Fetch the exact IMDb id for a TMDB movie id — no text-matching involved."""
    if not tmdb_id:
        return None
    url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/external_ids?api_key={TMDB_KEY}"
    try:
        resp = requests.get(url, timeout=10)
    except requests.exceptions.RequestException:
        return None
    if resp.status_code != 200:
        return None
    return resp.json().get("imdb_id")


def omdb_search_raw(query):
    """Hits OMDB's search (s=) endpoint and returns the raw list of results (or [])."""
    url = f"http://www.omdbapi.com/?s={query}&apikey={OMDB_KEY}"
    try:
        resp = requests.get(url, timeout=10)
    except requests.exceptions.RequestException:
        return []
    if resp.status_code != 200:
        return []
    data = resp.json()
    if data.get("Response") != "True":
        return []
    return [r for r in data.get("Search", []) if r.get("Type") == "movie"]


def _omdb_request(params):
    """Low-level OMDB GET with shared error handling. Returns dict or None."""
    url = f"http://www.omdbapi.com/?apikey={OMDB_KEY}"
    for key, value in params.items():
        url += f"&{key}={value}"
    try:
        resp = requests.get(url, timeout=10)
    except requests.exceptions.RequestException as e:
        st.error(f"Could not reach OMDB: {e}")
        return None

    if resp.status_code == 401:
        st.error("OMDB API key invalid or expired. Get a free key at http://www.omdbapi.com/apikey.aspx")
        return None
    if resp.status_code != 200:
        st.error(f"OMDB returned an error (status {resp.status_code}).")
        return None

    return resp.json()


def get_movie_omdb(name, alt_query=None, imdb_id=None):
    """
    Fetch movie details from OMDB, most-reliable method first:
      1. If we already have an exact IMDb id (from TMDB), use that.
      2. Otherwise try an exact title lookup.
      3. Otherwise fall back to OMDB's own search.
    """
    if imdb_id:
        data = _omdb_request({"i": imdb_id})
        if data and data.get("Response") == "True":
            return data

    data = _omdb_request({"t": name})
    if data and data.get("Response") == "True":
        return data

    candidates = omdb_search_raw(name)
    if alt_query and alt_query.strip().lower() != name.strip().lower():
        candidates += omdb_search_raw(alt_query)

    if candidates:
        reference = alt_query if alt_query else name
        best = max(candidates, key=lambda r: similarity(reference, r.get("Title", "")))
        imdb_id = best.get("imdbID")
        if imdb_id:
            by_id = _omdb_request({"i": imdb_id})
            if by_id and by_id.get("Response") == "True":
                return by_id

    return data


def get_tmdb_reviews(movie_id):
    if not movie_id:
        return []

    all_reviews = []
    for page in range(1, 4):
        reviews_url = f"https://api.themoviedb.org/3/movie/{movie_id}/reviews?api_key={TMDB_KEY}&page={page}"
        try:
            reviews_resp = requests.get(reviews_url, timeout=10)
        except requests.exceptions.RequestException:
            break

        if reviews_resp.status_code != 200:
            break

        page_results = reviews_resp.json().get("results", [])
        if not page_results:
            break
        all_reviews.extend([r["content"] for r in page_results])

    return all_reviews


# ---------------------------------------------------------------------
# NEW: real-time search-as-you-type using streamlit-searchbox.
# This function feeds st_searchbox — it is called on every keystroke
# (debounced) and must return a list of (label, value) tuples, where
# `value` is what gets stored when the user picks a suggestion.
# ---------------------------------------------------------------------
def search_movies_for_box(query):
    if not query or len(query.strip()) < 2:
        return []
    results = tmdb_search_raw(query.strip())
    options = []
    for r in results[:8]:
        title = r.get("title", "Untitled")
        year = r.get("release_date", "")[:4] if r.get("release_date") else ""
        label = f"{title} ({year})" if year else title
        options.append((label, r))  # (displayed label, full TMDB result dict)
    return options


st.title("Movie Sentiment Analyzer")

if "selected_movie" not in st.session_state:
    st.session_state.selected_movie = None

# Bumped every time we reset, so the searchbox gets a brand-new widget
# key and forgets its previously-picked value (otherwise it re-fires
# the old selection on the very next rerun).
if "searchbox_generation" not in st.session_state:
    st.session_state.searchbox_generation = 0

# If a movie is already selected, show a way to start a new search
if st.session_state.selected_movie:
    if st.button("🔄 Search a different movie"):
        st.session_state.selected_movie = None
        st.session_state.searchbox_generation += 1
        st.rerun()

if not st.session_state.selected_movie:
    picked = st_searchbox(
        search_movies_for_box,
        placeholder="Search a movie name...",
        label="Search a movie name:",
        key=f"movie_searchbox_{st.session_state.searchbox_generation}",
        clear_on_submit=False,
        debounce=300,  # ms delay after typing stops before hitting the API
    )

    if picked:
        st.session_state.selected_movie = picked
        st.rerun()

selected_movie = st.session_state.selected_movie

if selected_movie:
    correct_title = selected_movie.get("title")
    tmdb_id = selected_movie.get("id")

    imdb_id = tmdb_get_imdb_id(tmdb_id)
    data = get_movie_omdb(correct_title, alt_query=correct_title, imdb_id=imdb_id)

    if data and data.get("Response") == "True":
        col1, col2 = st.columns(2)

        with col1:
            if data.get("Poster", "N/A") != "N/A":
                st.image(data["Poster"])
            else:
                st.write("Poster unavailable")

        with col2:
            st.subheader(data.get("Title", correct_title))
            st.write(f"Year: {data.get('Year', 'N/A')}")
            st.write(f"Genre: {data.get('Genre', 'N/A')}")
            st.write(f"Director: {data.get('Director', 'N/A')}")
            st.write(f"Cast: {data.get('Actors', 'N/A')}")
            st.write(f"Runtime: {data.get('Runtime', 'N/A')}")
            st.write(f"Language: {data.get('Language', 'N/A')}")
            st.write(f"Country: {data.get('Country', 'N/A')}")
            st.write(f"Awards: {data.get('Awards', 'N/A')}")
            st.write(f"IMDB Rating: {data.get('imdbRating', 'N/A')}")
            if data.get("Ratings"):
                for r in data["Ratings"]:
                    st.write(f"{r['Source']}: {r['Value']}")
            st.write(f"Plot: {data.get('Plot', 'N/A')}")

        st.divider()

        with st.spinner("Fetching and analyzing reviews..."):
            reviews = get_tmdb_reviews(tmdb_id)

        if reviews:
            positive_reviews = []
            negative_reviews = []

            for review in reviews:
                cleaned = clean_text(review)
                cleaned = remove_stopwords(cleaned)
                transformed = tfidf.transform([cleaned])
                prediction = model.predict(transformed)
                score = model.predict_proba(transformed)

                if prediction[0] == 1:
                    positive_reviews.append((review[:200], round(score[0][1] * 100, 2)))
                else:
                    negative_reviews.append((review[:200], round(score[0][0] * 100, 2)))

            total = len(reviews)
            pos_percent = round(len(positive_reviews) / total * 100, 2)
            neg_percent = round(len(negative_reviews) / total * 100, 2)

            st.subheader("Overall Sentiment:")
            if pos_percent >= neg_percent:
                st.success(f"Positive - {pos_percent}% ({len(positive_reviews)}/{total} reviews positive)")
            else:
                st.error(f"Negative - {neg_percent}% ({len(negative_reviews)}/{total} reviews negative)")

            col3, col4 = st.columns(2)

            with col3:
                st.subheader("Positive Reviews:")
                if positive_reviews:
                    for r, s in positive_reviews[:3]:
                        st.success(f"{s}% — {r}...")
                else:
                    st.write("No Positive Review Found")

            with col4:
                st.subheader("Negative Reviews:")
                if negative_reviews:
                    for r, s in negative_reviews[:3]:
                        st.error(f"{s}% — {r}...")
                else:
                    st.write("No Negative Review Found")

        else:
            st.warning(
                "No reviews found in TMDB for this movie. Try a well-known Hollywood title "
                " niche/regional movies often have zero TMDB reviews."
            )

    elif data:
        st.error("Movie Not Found - Check The Movie Name!")