import streamlit as st

# MUST be the very first Streamlit command in the script
st.set_page_config(page_title="Movie Sentiment Analyzer", layout="wide")

import requests
import pickle
import re
from difflib import SequenceMatcher
from nltk.corpus import stopwords

model = pickle.load(open("model.pkl", "rb"))
tfidf = pickle.load(open("tfidf.pkl", "rb"))
stop_words = set(stopwords.words('english'))

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

    return resp.json().get("results", [])


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
    # Only keep actual movies — excludes unrelated TV series/episodes
    # that happen to share the exact same short title.
    return [r for r in data.get("Search", []) if r.get("Type") == "movie"]


def search_movie(name):
    """
    Typo-tolerant movie search (used only as a fallback helper — the
    main flow now uses the searchbox where the user picks an exact
    TMDB result, so this ambiguity-prone matching is no longer on the
    primary path, but is kept in case it's needed elsewhere).
    """
    tmdb_results = tmdb_search_raw(name)
    if tmdb_results:
        best = max(tmdb_results[:8], key=lambda r: similarity(name, r.get("title", "")))
        return best.get("title"), best.get("id")

    omdb_results = omdb_search_raw(name)
    if omdb_results:
        best = max(omdb_results, key=lambda r: similarity(name, r.get("Title", "")))
        corrected_title = best.get("Title")

        retry_results = tmdb_search_raw(corrected_title)
        if retry_results:
            tmdb_best = max(retry_results[:5], key=lambda r: similarity(corrected_title, r.get("title", "")))
            return tmdb_best.get("title"), tmdb_best.get("id")

        return corrected_title, None

    return None, None


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
      1. If we already have an exact IMDb id (from TMDB), use that —
         zero ambiguity, always the right movie.
      2. Otherwise try an exact title lookup.
      3. Otherwise fall back to OMDB's own search — trying both the
         resolved title and the user's raw input, filtered to actual
         movies only — and fetch by the best match's IMDb id.
    """
    if imdb_id:
        data = _omdb_request({"i": imdb_id})
        if data and data.get("Response") == "True":
            return data

    data = _omdb_request({"t": name})
    if data and data.get("Response") == "True":
        return data

    # Fallback: search OMDB with both the resolved title and the raw
    # user input, merge candidates, pick the closest match, fetch by id.
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


st.title("Movie Sentiment Analyzer")

try:
    from streamlit_searchbox import st_searchbox
except ImportError:
    st.error(
        "The `streamlit-searchbox` package isn't installed. Run "
        "`pip install streamlit-searchbox` in your terminal, then restart the app."
    )
    st.stop()


def search_movies_tmdb(searchterm: str):
    """
    Called by the searchbox on every keystroke (debounced internally).
    Returns a list of (label_shown_in_dropdown, value_passed_back) tuples.
    The value is the full TMDB result dict, so once the user picks one
    we already have its exact id — no fuzzy title-matching needed later.
    """
    if not searchterm or len(searchterm.strip()) < 2:
        return []

    results = tmdb_search_raw(searchterm)
    options = []
    for r in results[:8]:
        title = r.get("title", "Untitled")
        year = r.get("release_date", "")[:4] if r.get("release_date") else ""
        label = f"{title} ({year})" if year else title
        options.append((label, r))
    return options


selected_movie = st_searchbox(
    search_movies_tmdb,
    key="movie_searchbox",
    placeholder="Start typing a movie name...",
)

if selected_movie:
    correct_title = selected_movie.get("title")
    tmdb_id = selected_movie.get("id")

    # Step 1: get the exact IMDb id via TMDB — the user already picked
    # the exact movie from the dropdown, so there's zero ambiguity left.
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

        # Step 3: fetch reviews using the TMDB id directly (no re-search needed)
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