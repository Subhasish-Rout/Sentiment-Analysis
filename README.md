# 🎬 Movie Sentiment Analyzer

A Streamlit web app that lets you search for any movie and see how audiences feel about it. It combines movie data from **TMDB** and **OMDb** with sentiment analysis of real user reviews to give a quick, data-backed view of a film's reception.

## ✨ Features

- 🔍 **Real-time search suggestions**: suggestions appear as you type using `streamlit-searchbox`
- 🎞️ **Movie details**: title, release year, genre, runtime, cast, plot and more
- ⭐ **Ratings**: IMDb and other ratings pulled from OMDb, plus TMDB's audience score
- 🖼️ **Poster display**: high-quality poster fetched from TMDB
- 🧠 **Sentiment analysis**: overall sentiment (Positive / Negative) calculated from audience reviews using trained ML model & TF-IDF
- 💬 **Original user reviews**: real reviews from viewers, shown next to the sentiment result

## 🛠️ How It Works

1. Start typing a movie name and pick from the live suggestions.
2. The app fetches details and poster from **TMDB**, and ratings from **OMDb**.
3. Audience reviews are collected for the movie.
4. Each review is analyzed, and the overall sentiment score is calculated.
5. Results, poster, ratings and original reviews are displayed in one clean dashboard.

## 🧰 Tech Stack

- **Framework:** Streamlit
- **Language:** Python
- **APIs:** TMDB API, OMDb API
- **Machine Learning / NLP:** Scikit-Learn, TF-IDF, NLTK, Pandas, NumPy

## 🚀 Getting Started

### 1. Clone the repository
```bash
git clone https://github.com/Subhasish-Rout/Sentiment-Analysis.git
cd Sentiment-Analysis
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure API keys
Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`:
```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```
Add your free keys from [TMDB](https://www.themoviedb.org/settings/api) and [OMDb](https://www.omdbapi.com/apikey.aspx) in `.streamlit/secrets.toml`:
```toml
OMDB_KEY = "your_omdb_key"
TMDB_KEY = "your_tmdb_key"
```

### 4. Run the app
```bash
streamlit run app3.py
```

## 📸 Screenshots

<img width="1765" height="552" alt="Screenshot 2026-09-07 100417" src="https://github.com/user-attachments/assets/98c3cc83-6929-4aba-ac60-cf66b21a0bcd" />
<img width="1806" height="805" alt="Screenshot 2026-09-28 164111" src="https://github.com/user-attachments/assets/d2bac895-04ff-453a-9f9f-c42c74b8f2c1" />
<img width="1745" height="757" alt="Screenshot 2026-09-28 163743" src="https://github.com/user-attachments/assets/9c30000b-8502-4797-b391-76ad1f616eeb" />

## 🔮 Future Improvements

- Compare sentiment between multiple movies
- Add sentiment distribution charts
- Support more languages

## 🙏 Acknowledgements

- [TMDB](https://www.themoviedb.org/) for movie data and posters
- [OMDb API](https://www.omdbapi.com/) for ratings and extra details

> This product uses the TMDB API but is not endorsed or certified by TMDB.

## 📄 License

This project is licensed under the MIT License.
