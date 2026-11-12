/**
 * MEDIPORTAL247 - FRONTEND CLIENT
 * Handles responsive filtering, 20-movies-per-page pagination,
 * instant search suggestions, rich movie download details,
 * screenshots gallery, lightbox, and clipboard helpers.
 */

(() => {
  "use strict";

  // Application State
  const state = {
    page: 1,
    per_page: 20, // Strictly 20 movies in every page as requested
    pages: 1,
    total: 0,
    query: "",
    category: "all",
    language: "",
    genre: "",
    quality: "",
    year: "",
    sort: "newest",
    activeMovieId: null,
    requestToken: 0,
    featuredList: [],
    currentSlide: 0,
    slideInterval: null,
  };

  // DOM Elements
  const DOM = {
    // Header & Search
    mainHeader: document.querySelector("#main-header"),
    headerSearchForm: document.querySelector("#header-search-form"),
    headerSearchInput: document.querySelector("#header-search-input"),
    headerSearchClear: document.querySelector("#header-search-clear"),
    searchSuggestions: document.querySelector("#search-suggestions"),
    suggestionsList: document.querySelector("#suggestions-list"),
    desktopNav: document.querySelector(".desktop-nav"),
    desktopGenresDropdown: document.querySelector("#desktop-genres-dropdown"),
    desktopYearsDropdown: document.querySelector("#desktop-years-dropdown"),
    menuToggle: document.querySelector("#menu-toggle"),

    // Mobile Drawer
    mobileDrawer: document.querySelector("#mobile-drawer"),
    drawerBackdrop: document.querySelector("#drawer-backdrop"),
    drawerClose: document.querySelector("#drawer-close"),
    drawerGenresList: document.querySelector("#drawer-genres-list"),
    drawerYearsList: document.querySelector("#drawer-years-list"),

    // Quick Pills & Featured Slider
    categoryPills: document.querySelector("#category-pills"),
    featuredSlider: document.querySelector("#featured-slider"),
    sliderDots: document.querySelector("#slider-dots"),
    prevSlideBtn: document.querySelector("#prev-slide"),
    nextSlideBtn: document.querySelector("#next-slide"),

    // Filter Toolbar
    filterSearchInput: document.querySelector("#filter-search-input"),
    categorySelect: document.querySelector("#category-select"),
    languageSelect: document.querySelector("#language-select"),
    genreSelect: document.querySelector("#genre-select"),
    qualitySelect: document.querySelector("#quality-select"),
    yearSelect: document.querySelector("#year-select"),
    sortSelect: document.querySelector("#sort-select"),
    resetFiltersBtn: document.querySelector("#reset-filters-btn"),
    activeTagsRow: document.querySelector("#active-tags-row"),
    tagsContainer: document.querySelector("#tags-container"),
    clearAllTagsBtn: document.querySelector("#clear-all-tags-btn"),

    // Grid & Results
    moviesGrid: document.querySelector("#movies-grid"),
    resultsCountBadge: document.querySelector("#results-count-badge"),
    catalogTitle: document.querySelector("#catalog-title"),
    statusBanner: document.querySelector("#status-banner"),
    statusMessage: document.querySelector("#status-message"),
    statusRetryBtn: document.querySelector("#status-retry-btn"),
    emptyState: document.querySelector("#empty-state"),
    emptyResetBtn: document.querySelector("#empty-reset-btn"),
    emptyBrowseBtn: document.querySelector("#empty-browse-btn"),

    // Pagination
    paginationBar: document.querySelector("#pagination-bar"),
    paginationInfo: document.querySelector("#pagination-info"),
    paginationLinks: document.querySelector("#pagination-links"),
    pageJumpInput: document.querySelector("#page-jump-input"),
    pageJumpBtn: document.querySelector("#page-jump-btn"),

    // Movie Detail Modal
    movieModal: document.querySelector("#movie-modal"),
    modalBackdropClose: document.querySelector("#modal-backdrop-close"),
    modalCloseBtn: document.querySelector("#modal-close-btn"),
    modalLoading: document.querySelector("#modal-loading"),
    modalBody: document.querySelector("#modal-body"),
    modalBcHome: document.querySelector("#modal-bc-home"),
    modalBcCategory: document.querySelector("#modal-bc-category"),
    modalBcTitle: document.querySelector("#modal-bc-title"),
    modalMovieTitle: document.querySelector("#modal-movie-title"),
    modalHeaderBadges: document.querySelector("#modal-header-badges"),
    modalPosterImg: document.querySelector("#modal-poster-img"),
    modalSpecsList: document.querySelector("#modal-specs-list"),
    modalStorylineText: document.querySelector("#modal-storyline-text"),
    modalTrailerContainer: document.querySelector("#modal-trailer-container"),
    modalTrailerEmbed: document.querySelector("#modal-trailer-embed"),
    modalScreenshotsSection: document.querySelector("#modal-screenshots-section"),
    modalScreenshotsGrid: document.querySelector("#modal-screenshots-grid"),
    modalDownloadTiers: document.querySelector("#modal-download-tiers"),
    modalDownloadFallback: document.querySelector("#modal-download-fallback"),
    modalSourceLink: document.querySelector("#modal-source-link"),
    modalRelatedGrid: document.querySelector("#modal-related-grid"),

    // Lightbox & Toast
    lightboxModal: document.querySelector("#lightbox-modal"),
    lightboxImg: document.querySelector("#lightbox-img"),
    lightboxClose: document.querySelector("#lightbox-close"),
    toastNotification: document.querySelector("#toast-notification"),
    toastMessage: document.querySelector("#toast-message"),

    // Footer & Stats
    libraryStatusBadge: document.querySelector("#library-status-badge"),
    footerTotalCount: document.querySelector("#footer-total-count"),
    footerUpdatedAt: document.querySelector("#footer-updated-at"),
  };

  // SVG Fallback for missing/broken posters
  const FALLBACK_POSTER_SVG =
    "data:image/svg+xml;charset=utf-8," +
    encodeURIComponent(`
      <svg xmlns="http://www.w3.org/2000/svg" width="300" height="450" viewBox="0 0 300 450">
        <rect width="300" height="450" fill="#111a2e"/>
        <circle cx="150" cy="180" r="45" fill="#1e293b"/>
        <path d="M135 160 L175 180 L135 200 Z" fill="#00e5ff"/>
        <text x="150" y="270" font-family="sans-serif" font-size="16" font-weight="bold" fill="#94a3b8" text-anchor="middle">MEDIPORTAL247</text>
        <text x="150" y="295" font-family="sans-serif" font-size="12" fill="#64748b" text-anchor="middle">Poster Preview</text>
      </svg>
    `);

  // Utilities
  function formatNumber(num) {
    return new Intl.NumberFormat().format(num || 0);
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  async function getJson(url, signal) {
    const response = await fetch(url, {
      signal,
      headers: { Accept: "application/json" },
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || `HTTP error ${response.status}`);
    }
    return data;
  }

  function showToast(message) {
    if (!DOM.toastNotification) return;
    DOM.toastMessage.textContent = message;
    DOM.toastNotification.hidden = false;
    window.clearTimeout(DOM.toastNotification._timer);
    DOM.toastNotification._timer = window.setTimeout(() => {
      DOM.toastNotification.hidden = true;
    }, 3000);
  }

  function copyToClipboard(text, successMsg = "Link copied to clipboard!") {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(
        () => showToast(successMsg),
        () => fallbackCopy(text, successMsg)
      );
    } else {
      fallbackCopy(text, successMsg);
    }
  }

  function fallbackCopy(text, successMsg) {
    const textArea = document.createElement("textarea");
    textArea.value = text;
    textArea.style.position = "fixed";
    textArea.style.left = "-9999px";
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    try {
      document.execCommand("copy");
      showToast(successMsg);
    } catch (e) {
      showToast("Could not auto-copy. Please copy manually.");
    }
    document.body.removeChild(textArea);
  }

  // URL Query Parameters Sync
  function syncStateFromUrl() {
    const params = new URLSearchParams(window.location.search);
    state.query = params.get("q") || "";
    
    // Check category from URL param or initial window context
    const catMatch = window.location.pathname.match(/\/category\/([a-z0-9_-]+)/i);
    if (catMatch) {
      state.category = catMatch[1];
    } else if (window.INITIAL_CATEGORY) {
      state.category = window.INITIAL_CATEGORY;
    } else {
      state.category = params.get("category") || "all";
    }

    state.language = params.get("language") || "";

    // Check genre from URL pathname or initial window context
    const genreMatch = window.location.pathname.match(/\/genre\/([a-z0-9_%-]+)/i);
    if (genreMatch) {
      state.genre = decodeURIComponent(genreMatch[1]);
    } else if (window.INITIAL_GENRE) {
      state.genre = window.INITIAL_GENRE;
    } else {
      state.genre = params.get("genre") || "";
    }

    state.quality = params.get("quality") || "";

    // Check year from URL pathname or initial window context
    const yearMatch = window.location.pathname.match(/\/year\/(\d+)/i);
    if (yearMatch) {
      state.year = yearMatch[1];
    } else if (window.INITIAL_YEAR) {
      state.year = window.INITIAL_YEAR;
    } else {
      state.year = params.get("year") || "";
    }

    state.sort = params.get("sort") || "newest";

    // Check page from pathname e.g. /page/3 or query param
    const pageMatch = window.location.pathname.match(/\/page\/(\d+)/i);
    if (pageMatch) {
      state.page = Math.max(1, parseInt(pageMatch[1], 10));
    } else if (window.INITIAL_PAGE) {
      state.page = Math.max(1, parseInt(window.INITIAL_PAGE, 10));
    } else {
      state.page = Math.max(1, parseInt(params.get("page") || "1", 10));
    }

    // Check movie detail query or initial movie id
    const movieParam = params.get("movie");
    if (movieParam) {
      state.activeMovieId = movieParam;
    } else if (window.INITIAL_MOVIE_ID) {
      state.activeMovieId = window.INITIAL_MOVIE_ID;
    }

    updateToolbarInputs();
  }

  function pushStateToUrl(replace = false) {
    const params = new URLSearchParams();
    if (state.query) params.set("q", state.query);
    if (state.category && state.category !== "all") params.set("category", state.category);
    if (state.language) params.set("language", state.language);
    if (state.genre) params.set("genre", state.genre);
    if (state.quality) params.set("quality", state.quality);
    if (state.year) params.set("year", state.year);
    if (state.sort && state.sort !== "newest") params.set("sort", state.sort);
    if (state.page > 1) params.set("page", String(state.page));
    if (state.activeMovieId) params.set("movie", state.activeMovieId);

    const queryString = params.toString();
    const basePath = window.location.pathname.startsWith("/movie/") ? "/" : window.location.pathname;
    const cleanPath = basePath.replace(/\/page\/\d+/i, "") || "/";
    const newUrl = queryString ? `${cleanPath}?${queryString}` : cleanPath;

    if (replace) {
      history.replaceState({ ...state }, "", newUrl);
    } else {
      history.pushState({ ...state }, "", newUrl);
    }
  }

  function updateToolbarInputs() {
    if (DOM.filterSearchInput) DOM.filterSearchInput.value = state.query;
    if (DOM.headerSearchInput) DOM.headerSearchInput.value = state.query;
    if (DOM.headerSearchClear) DOM.headerSearchClear.hidden = !state.query;
    if (DOM.categorySelect) DOM.categorySelect.value = state.category;
    if (DOM.languageSelect) DOM.languageSelect.value = state.language;
    if (DOM.genreSelect) DOM.genreSelect.value = state.genre;
    if (DOM.qualitySelect) DOM.qualitySelect.value = state.quality;
    if (DOM.yearSelect) DOM.yearSelect.value = state.year;
    if (DOM.sortSelect) DOM.sortSelect.value = state.sort;

    updateQuickPillsActive();
    updateDesktopNavActive();
    renderActiveTagChips();
  }

  function updateQuickPillsActive() {
    if (!DOM.categoryPills) return;
    const pills = DOM.categoryPills.querySelectorAll(".pill-chip");
    pills.forEach((pill) => {
      let isActive = false;
      if (pill.dataset.category) {
        isActive = pill.dataset.category === state.category;
      } else if (pill.dataset.quality) {
        isActive = pill.dataset.quality.toLowerCase() === state.quality.toLowerCase();
      } else if (pill.dataset.genre) {
        isActive = pill.dataset.genre.toLowerCase() === state.genre.toLowerCase();
      }
      pill.classList.toggle("active", isActive);
    });
  }

  function updateDesktopNavActive() {
    if (!DOM.desktopNav) return;
    const links = DOM.desktopNav.querySelectorAll(".nav-link[data-category]");
    links.forEach((link) => {
      link.classList.toggle("active", link.dataset.category === state.category);
    });
  }

  function renderActiveTagChips() {
    if (!DOM.tagsContainer || !DOM.activeTagsRow) return;
    DOM.tagsContainer.replaceChildren();

    const activeFilters = [];
    if (state.query) activeFilters.push({ key: "query", label: `Search: "${state.query}"` });
    if (state.category && state.category !== "all") {
      activeFilters.push({ key: "category", label: `Category: ${state.category.replace("-", " ")}` });
    }
    if (state.language) activeFilters.push({ key: "language", label: `Language: ${state.language}` });
    if (state.genre) activeFilters.push({ key: "genre", label: `Genre: ${state.genre}` });
    if (state.quality) activeFilters.push({ key: "quality", label: `Quality: ${state.quality}` });
    if (state.year) activeFilters.push({ key: "year", label: `Year: ${state.year}` });

    if (activeFilters.length === 0) {
      DOM.activeTagsRow.hidden = true;
      return;
    }

    DOM.activeTagsRow.hidden = false;
    activeFilters.forEach((filter) => {
      const chip = document.createElement("span");
      chip.className = "active-tag-chip";
      chip.innerHTML = `${escapeHtml(filter.label)} <span aria-hidden="true">✕</span>`;
      chip.addEventListener("click", () => {
        if (filter.key === "query") state.query = "";
        if (filter.key === "category") state.category = "all";
        if (filter.key === "language") state.language = "";
        if (filter.key === "genre") state.genre = "";
        if (filter.key === "quality") state.quality = "";
        if (filter.key === "year") state.year = "";
        state.page = 1;
        updateToolbarInputs();
        pushStateToUrl();
        loadMovies();
      });
      DOM.tagsContainer.appendChild(chip);
    });
  }

  // Load Filter Options from API
  async function loadFilters() {
    try {
      const data = await getJson("/api/filters");

      // Languages
      if (DOM.languageSelect && data.languages) {
        DOM.languageSelect.replaceChildren(new Option("All Languages", ""));
        data.languages.forEach((lang) => {
          DOM.languageSelect.add(new Option(lang, lang));
        });
        DOM.languageSelect.value = state.language;
      }

      // Genres
      if (DOM.genreSelect && data.genres) {
        DOM.genreSelect.replaceChildren(new Option("All Genres", ""));
        data.genres.forEach((genre) => {
          DOM.genreSelect.add(new Option(genre, genre));
        });
        DOM.genreSelect.value = state.genre;
      }

      // Years
      if (DOM.yearSelect && data.years) {
        DOM.yearSelect.replaceChildren(new Option("All Years", ""));
        DOM.yearSelect.add(new Option("2026", "2026"));
        DOM.yearSelect.add(new Option("2025", "2025"));
        DOM.yearSelect.add(new Option("2024", "2024"));
        DOM.yearSelect.add(new Option("2023", "2023"));
        DOM.yearSelect.add(new Option("2022", "2022"));
        DOM.yearSelect.add(new Option("2021", "2021"));
        DOM.yearSelect.add(new Option("2020", "2020"));
        DOM.yearSelect.add(new Option("2010–2019", "2010s"));
        DOM.yearSelect.add(new Option("2000–2009", "2000s"));
        DOM.yearSelect.add(new Option("1990–1999", "1990s"));
        DOM.yearSelect.add(new Option("Classics (< 1990)", "classic"));
        DOM.yearSelect.value = state.year;
      }

      // Populate Mobile Drawer Chips
      if (DOM.drawerGenresList && data.genres) {
        DOM.drawerGenresList.replaceChildren();
        data.genres.slice(0, 16).forEach((genre) => {
          const chip = document.createElement("button");
          chip.type = "button";
          chip.className = "drawer-chip";
          chip.textContent = genre;
          chip.addEventListener("click", () => {
            state.genre = genre;
            state.page = 1;
            closeMobileDrawer();
            updateToolbarInputs();
            pushStateToUrl();
            loadMovies();
          });
          DOM.drawerGenresList.appendChild(chip);
        });
      }

      if (DOM.drawerYearsList) {
        const years = ["2026", "2025", "2024", "2023", "2022", "2021", "2020", "2010s", "2000s"];
        DOM.drawerYearsList.replaceChildren();
        years.forEach((yr) => {
          const chip = document.createElement("button");
          chip.type = "button";
          chip.className = "drawer-chip";
          chip.textContent = yr;
          chip.addEventListener("click", () => {
            state.year = yr;
            state.page = 1;
            closeMobileDrawer();
            updateToolbarInputs();
            pushStateToUrl();
            loadMovies();
          });
          DOM.drawerYearsList.appendChild(chip);
        });
      }

      // Stats badge
      if (DOM.libraryStatusBadge && data.total) {
        DOM.libraryStatusBadge.textContent = `${formatNumber(data.total)} TITLES INDEXED`;
      }
      if (DOM.footerTotalCount && data.total) {
        DOM.footerTotalCount.textContent = `${formatNumber(data.total)}+`;
      }
    } catch (error) {
      console.warn("Could not load filters:", error);
    }
  }

  // Load Featured Carousel
  async function loadFeatured() {
    try {
      const data = await getJson("/api/featured");
      if (!data.featured || data.featured.length === 0) return;
      state.featuredList = data.featured;
      renderFeaturedSlider();
    } catch (e) {
      console.warn("Could not load featured slider:", e);
    }
  }

  function renderFeaturedSlider() {
    if (!DOM.featuredSlider || !DOM.sliderDots) return;
    DOM.featuredSlider.replaceChildren();
    DOM.sliderDots.replaceChildren();

    state.featuredList.forEach((movie, index) => {
      const slide = document.createElement("div");
      slide.className = `featured-slide${index === 0 ? " active" : ""}`;

      const thumbSrc = movie.thumbnail || FALLBACK_POSTER_SVG;
      slide.innerHTML = `
        <img class="slide-backdrop-img" src="${escapeHtml(thumbSrc)}" alt="" aria-hidden="true" onerror="this.src='${FALLBACK_POSTER_SVG}'">
        <div class="slide-overlay"></div>
        <div class="slide-inner">
          <img class="slide-poster" src="${escapeHtml(thumbSrc)}" alt="${escapeHtml(movie.title)}" onerror="this.src='${FALLBACK_POSTER_SVG}'">
          <div class="slide-info">
            <span class="slide-tag">🔥 FEATURED SPOTLIGHT</span>
            <h2 class="slide-title">${escapeHtml(movie.full_name || movie.title)}</h2>
            <div class="slide-badges">
              ${movie.year ? `<span class="badge badge-year">${escapeHtml(movie.year)}</span>` : ""}
              ${movie.rating ? `<span class="badge badge-rating">★ ${escapeHtml(movie.rating)} IMDb</span>` : ""}
              ${movie.quality ? `<span class="badge badge-quality">${escapeHtml(movie.quality.split("|")[0])}</span>` : ""}
              ${movie.language ? `<span class="badge badge-audio">${escapeHtml(movie.language)}</span>` : ""}
            </div>
            <p class="slide-storyline">${escapeHtml(movie.genres || "Top rated blockbuster available for high-speed download")}</p>
            <div class="slide-cta-row">
              <button class="btn btn-primary" type="button" data-action="download" data-id="${escapeHtml(movie.id)}">
                ⚡ Download Now
              </button>
              <button class="btn btn-secondary" type="button" data-action="details" data-id="${escapeHtml(movie.id)}">
                ℹ️ Technical Specs
              </button>
            </div>
          </div>
        </div>
      `;

      slide.querySelectorAll("button[data-id]").forEach((btn) => {
        btn.addEventListener("click", () => openMovieDetails(btn.dataset.id));
      });

      DOM.featuredSlider.appendChild(slide);

      // Dot
      const dot = document.createElement("button");
      dot.className = `slider-dot${index === 0 ? " active" : ""}`;
      dot.setAttribute("aria-label", `Slide ${index + 1}`);
      dot.addEventListener("click", () => goToSlide(index));
      DOM.sliderDots.appendChild(dot);
    });

    startSlideTimer();
  }

  function goToSlide(index) {
    const slides = DOM.featuredSlider.querySelectorAll(".featured-slide");
    const dots = DOM.sliderDots.querySelectorAll(".slider-dot");
    if (!slides.length) return;

    state.currentSlide = (index + slides.length) % slides.length;
    slides.forEach((s, idx) => s.classList.toggle("active", idx === state.currentSlide));
    dots.forEach((d, idx) => d.classList.toggle("active", idx === state.currentSlide));
  }

  function startSlideTimer() {
    window.clearInterval(state.slideInterval);
    state.slideInterval = window.setInterval(() => {
      goToSlide(state.currentSlide + 1);
    }, 6000);
  }

  // Load Movies Grid (20 Movies in Every Page)
  async function loadMovies() {
    const token = ++state.requestToken;
    clearError();
    renderSkeletons(state.per_page);

    const params = new URLSearchParams({
      page: String(state.page),
      per_page: String(state.per_page), // 20 movies per page
      sort: state.sort,
    });
    if (state.query) params.set("q", state.query);
    if (state.category && state.category !== "all") params.set("category", state.category);
    if (state.language) params.set("language", state.language);
    if (state.genre) params.set("genre", state.genre);
    if (state.quality) params.set("quality", state.quality);
    if (state.year) params.set("year", state.year);

    try {
      const data = await getJson(`/api/movies?${params}`);
      if (token !== state.requestToken) return;

      state.pages = data.pages;
      state.total = data.total;

      renderMovieGrid(data.items);
      renderPagination();

      // Results badge
      if (DOM.resultsCountBadge) {
        const startItem = data.total > 0 ? (state.page - 1) * state.per_page + 1 : 0;
        const endItem = Math.min(state.page * state.per_page, data.total);
        DOM.resultsCountBadge.textContent =
          data.total > 0
            ? `Showing ${startItem}–${endItem} of ${formatNumber(data.total)} movies`
            : "0 movies found";
      }

      // Title heading
      if (DOM.catalogTitle) {
        if (state.query) {
          DOM.catalogTitle.textContent = `Search results for "${state.query}"`;
        } else if (state.category && state.category !== "all") {
          const catNames = {
            "dual-audio": "Dual Audio [Hindi-English] Movies",
            bollywood: "Bollywood Movies (Hindi)",
            hollywood: "Hollywood Movies",
            "web-series": "Web Series & TV Shows",
            "south-dubbed": "South Indian Hindi Dubbed Movies",
            "4k": "4K Ultra HD Movies",
          };
          DOM.catalogTitle.textContent = catNames[state.category] || "Latest Movie Releases";
        } else if (state.genre) {
          DOM.catalogTitle.textContent = `${state.genre} Movies`;
        } else {
          DOM.catalogTitle.textContent = "Latest Movie & Series Downloads";
        }
      }

      DOM.emptyState.hidden = data.items.length > 0;
      DOM.paginationBar.hidden = data.items.length === 0;
    } catch (error) {
      if (token !== state.requestToken) return;
      showError(error.message || "Could not connect to the movie database.");
      DOM.moviesGrid.replaceChildren();
      DOM.emptyState.hidden = true;
      DOM.paginationBar.hidden = true;
    }
  }

  function renderSkeletons(count = 20) {
    if (!DOM.moviesGrid) return;
    DOM.moviesGrid.replaceChildren();
    for (let i = 0; i < count; i++) {
      const sk = document.createElement("div");
      sk.className = "card-skeleton";
      DOM.moviesGrid.appendChild(sk);
    }
  }

  function renderMovieGrid(movies) {
    if (!DOM.moviesGrid) return;
    DOM.moviesGrid.replaceChildren();

    movies.forEach((movie) => {
      const card = document.createElement("article");
      card.className = "movie-card";
      card.tabIndex = 0;
      card.setAttribute("role", "button");
      card.setAttribute("aria-label", `Download ${movie.title}`);

      const thumbSrc = movie.thumbnail || FALLBACK_POSTER_SVG;
      const cleanRating = movie.rating ? `★ ${movie.rating}` : "";
      const qualitySnippet = movie.quality ? movie.quality.split("|")[0].trim() : "HD";
      const audioSnippet = movie.is_dual ? "Dual Audio" : movie.language.split("|")[0].trim();
      const metaRow = [movie.year, movie.format, movie.size].filter(Boolean).join(" • ");

      card.innerHTML = `
        <div class="card-poster-wrap">
          <img class="card-poster-img" src="${escapeHtml(thumbSrc)}" alt="${escapeHtml(movie.title)}" loading="lazy" onerror="this.src='${FALLBACK_POSTER_SVG}'">
          ${cleanRating ? `<span class="card-badge-rating">${escapeHtml(cleanRating)}</span>` : ""}
          ${qualitySnippet ? `<span class="card-badge-quality">${escapeHtml(qualitySnippet)}</span>` : ""}
          ${audioSnippet ? `<span class="card-badge-audio">${escapeHtml(audioSnippet)}</span>` : ""}
          ${movie.subtitle ? `<span class="card-badge-sub">ESub</span>` : ""}
          <div class="card-hover-overlay">
            <span class="card-download-btn">⚡ Download</span>
          </div>
        </div>
        <div class="card-body">
          <div class="card-meta-row">${escapeHtml(metaRow || "Catalogue Title")}</div>
          <h3 class="card-title">${escapeHtml(movie.full_name || movie.title)}</h3>
          <div class="card-genres">${escapeHtml(movie.genres || "Movie / Series")}</div>
          <div class="card-footer">
            <span class="card-dl-count">📥 ${movie.downloads_count || 1} Qualities</span>
            <span class="card-size">${escapeHtml(movie.size ? movie.size.split("|")[0] : "")}</span>
          </div>
        </div>
      `;

      card.addEventListener("click", () => openMovieDetails(movie.id));
      card.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          openMovieDetails(movie.id);
        }
      });

      DOM.moviesGrid.appendChild(card);
    });
  }

  // Pagination (Strictly 20 Movies Per Page)
  function renderPagination() {
    if (!DOM.paginationLinks || !DOM.paginationInfo) return;
    DOM.paginationLinks.replaceChildren();

    DOM.paginationInfo.textContent = `Page ${state.page} of ${state.pages} (${state.per_page} movies/page)`;
    if (state.pages <= 1) return;

    const makeBtn = (label, targetPage, disabled = false, current = false) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `page-btn${current ? " active" : ""}`;
      btn.textContent = label;
      btn.disabled = disabled;
      if (current) btn.setAttribute("aria-current", "page");
      btn.addEventListener("click", () => {
        if (targetPage !== state.page) {
          state.page = targetPage;
          pushStateToUrl();
          loadMovies();
          scrollToGrid();
        }
      });
      return btn;
    };

    // First & Prev
    DOM.paginationLinks.appendChild(makeBtn("« First", 1, state.page === 1));
    DOM.paginationLinks.appendChild(makeBtn("‹ Prev", Math.max(1, state.page - 1), state.page === 1));

    // Numbered pages with window
    const windowSize = 5;
    let startPage = Math.max(1, state.page - 2);
    let endPage = Math.min(state.pages, startPage + windowSize - 1);

    if (endPage - startPage < windowSize - 1) {
      startPage = Math.max(1, endPage - windowSize + 1);
    }

    if (startPage > 1) {
      DOM.paginationLinks.appendChild(makeBtn("1", 1, false, state.page === 1));
      if (startPage > 2) {
        const dots = document.createElement("span");
        dots.className = "page-ellipsis";
        dots.textContent = "…";
        DOM.paginationLinks.appendChild(dots);
      }
    }

    for (let p = startPage; p <= endPage; p++) {
      DOM.paginationLinks.appendChild(makeBtn(String(p), p, false, p === state.page));
    }

    if (endPage < state.pages) {
      if (endPage < state.pages - 1) {
        const dots = document.createElement("span");
        dots.className = "page-ellipsis";
        dots.textContent = "…";
        DOM.paginationLinks.appendChild(dots);
      }
      DOM.paginationLinks.appendChild(makeBtn(String(state.pages), state.pages, false, state.page === state.pages));
    }

    // Next & Last
    DOM.paginationLinks.appendChild(makeBtn("Next ›", Math.min(state.pages, state.page + 1), state.page === state.pages));
    DOM.paginationLinks.appendChild(makeBtn("Last »", state.pages, state.page === state.pages));

    if (DOM.pageJumpInput) {
      DOM.pageJumpInput.max = state.pages;
    }
  }

  function scrollToGrid() {
    const el = document.querySelector("#library");
    if (el) el.scrollIntoView({ behavior: "smooth" });
  }

  function showError(msg) {
    if (!DOM.statusBanner) return;
    DOM.statusMessage.textContent = msg;
    DOM.statusBanner.hidden = false;
  }

  function clearError() {
    if (!DOM.statusBanner) return;
    DOM.statusBanner.hidden = true;
  }

  // Open Full Movie Details Modal (MediPortal247 Layout)
  async function openMovieDetails(movieId) {
    if (!movieId || !DOM.movieModal) return;

    state.activeMovieId = movieId;
    pushStateToUrl();

    DOM.modalLoading.hidden = false;
    DOM.modalBody.hidden = true;
    DOM.movieModal.showModal();

    try {
      const movie = await getJson(`/api/movie?id=${encodeURIComponent(movieId)}`);
      DOM.modalLoading.hidden = true;
      DOM.modalBody.hidden = false;

      // Breadcrumbs
      DOM.modalBcTitle.textContent = movie.title || "Details";
      const catName = movie.is_series ? "Web Series" : movie.is_dual ? "Dual Audio" : "Movies";
      DOM.modalBcCategory.textContent = catName;

      // Header Banner
      DOM.modalMovieTitle.textContent = movie.full_name || movie.title;
      DOM.modalHeaderBadges.replaceChildren();

      const addHeaderBadge = (text, cls) => {
        if (!text) return;
        const b = document.createElement("span");
        b.className = `badge ${cls}`;
        b.textContent = text;
        DOM.modalHeaderBadges.appendChild(b);
      };

      if (movie.year) addHeaderBadge(movie.year, "badge-year");
      if (movie.rating) addHeaderBadge(`★ ${movie.rating} IMDb`, "badge-rating");
      if (movie.quality) addHeaderBadge(movie.quality, "badge-quality");
      if (movie.language) addHeaderBadge(movie.language, "badge-audio");
      if (movie.format) addHeaderBadge(movie.format, "badge-format");

      // Poster
      const posterSrc = movie.thumbnail || movie.thumbnail_url || FALLBACK_POSTER_SVG;
      DOM.modalPosterImg.src = posterSrc;
      DOM.modalPosterImg.onerror = () => {
        DOM.modalPosterImg.src = FALLBACK_POSTER_SVG;
      };

      // Technical Specs (Every Piece of Data)
      DOM.modalSpecsList.replaceChildren();

      const addSpecItem = (term, value, isLink = false, linkHref = "") => {
        if (!value) return;
        const dt = document.createElement("dt");
        dt.textContent = term + ":";
        const dd = document.createElement("dd");
        if (isLink && linkHref) {
          const a = document.createElement("a");
          a.href = linkHref;
          a.target = "_blank";
          a.rel = "noopener noreferrer";
          a.className = "imdb-link";
          a.innerHTML = `${escapeHtml(value)} ↗`;
          dd.appendChild(a);
        } else {
          dd.textContent = value;
        }
        DOM.modalSpecsList.append(dt, dd);
      };

      addSpecItem("Full Name", movie.full_name || movie.title);
      addSpecItem("Release Year", movie.year);
      addSpecItem("Language / Audio", movie.language);
      addSpecItem("Genres", movie.genres || movie.imdb_genres);
      if (movie.rating) {
        addSpecItem("IMDb Rating", `${movie.rating}/10`, Boolean(movie.imdb_url), movie.imdb_url);
      }
      addSpecItem("Director", movie.director);
      addSpecItem("Writer", movie.writer);
      addSpecItem("Stars / Cast", movie.cast || movie.stars);
      addSpecItem("Video Quality", movie.quality);
      addSpecItem("File Size", movie.size);
      addSpecItem("Container Format", movie.format);
      addSpecItem("Video Source", movie.source);
      addSpecItem("Subtitles", movie.subtitle);
      addSpecItem("Duration", movie.duration);
      addSpecItem("Season / Series", movie.season);
      addSpecItem("Date Added", movie.published_date || movie.scraped_at);
      if (movie.url) {
        addSpecItem("Source Post", "Original Source Page", true, movie.url);
      }

      // Storyline
      DOM.modalStorylineText.textContent =
        movie.storyline || movie.summary || "No storyline description available for this release.";

      // Official Trailer
      if (movie.trailer_url) {
        DOM.modalTrailerContainer.hidden = false;
        DOM.modalTrailerEmbed.innerHTML = `
          <iframe
            src="${escapeHtml(movie.trailer_url)}"
            title="Official Trailer"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowfullscreen
            loading="lazy"
          ></iframe>
        `;
      } else {
        DOM.modalTrailerContainer.hidden = true;
        DOM.modalTrailerEmbed.replaceChildren();
      }

      // Screenshots Gallery
      if (movie.post_screenshot_urls && movie.post_screenshot_urls.length > 0) {
        DOM.modalScreenshotsSection.hidden = false;
        DOM.modalScreenshotsGrid.replaceChildren();
        movie.post_screenshot_urls.forEach((url) => {
          const wrap = document.createElement("div");
          wrap.className = "screenshot-thumb-wrap";
          wrap.innerHTML = `<img src="${escapeHtml(url)}" alt="Movie Screenshot" loading="lazy">`;
          wrap.addEventListener("click", () => openLightbox(url));
          DOM.modalScreenshotsGrid.appendChild(wrap);
        });
      } else {
        DOM.modalScreenshotsSection.hidden = true;
      }

      // Download Links Section
      renderDownloadTiers(movie);

      // Related Movies
      renderRelatedMovies(movie.related || []);
    } catch (error) {
      DOM.modalLoading.hidden = true;
      DOM.modalBody.hidden = false;
      DOM.modalMovieTitle.textContent = "Error Loading Movie";
      DOM.modalStorylineText.textContent = error.message || "Failed to load movie details.";
      DOM.modalSpecsList.replaceChildren();
      DOM.modalDownloadTiers.replaceChildren();
    }
  }

  function renderDownloadTiers(movie) {
    if (!DOM.modalDownloadTiers) return;
    DOM.modalDownloadTiers.replaceChildren();

    const downloads = movie.downloads || [];
    if (downloads.length === 0) {
      DOM.modalDownloadFallback.hidden = false;
      if (movie.url && DOM.modalSourceLink) {
        DOM.modalSourceLink.href = movie.url;
      }
      return;
    }

    DOM.modalDownloadFallback.hidden = true;

    downloads.forEach((tier) => {
      const card = document.createElement("div");
      card.className = "tier-card";

      const tierHeader = document.createElement("div");
      tierHeader.className = "tier-header";
      tierHeader.innerHTML = `
        <h3 class="tier-title">${escapeHtml(tier.quality_tier)}</h3>
        <div class="tier-badges">
          ${tier.tier_badge ? `<span class="tier-badge">${escapeHtml(tier.tier_badge)}</span>` : ""}
          ${tier.size_badge ? `<span class="tier-size">${escapeHtml(tier.size_badge)}</span>` : ""}
        </div>
      `;

      const btnGrid = document.createElement("div");
      btnGrid.className = "tier-buttons-grid";

      (tier.links || []).forEach((linkObj) => {
        const link = linkObj.link;
        const label = linkObj.label || "Download";
        const labelLower = label.toLowerCase();

        let btnClass = "dl-btn-mirror";
        let icon = "🔗";

        if (labelLower.includes("google") || labelLower.includes("drive") || labelLower.includes("gdrive")) {
          btnClass = "dl-btn-gdrive";
          icon = "⚡";
        } else if (labelLower.includes("cloud") || labelLower.includes("fast") || labelLower.includes("hub")) {
          btnClass = "dl-btn-cloud";
          icon = "☁️";
        } else if (labelLower.includes("direct")) {
          btnClass = "dl-btn-direct";
          icon = "⬇️";
        }

        const a = document.createElement("a");
        a.className = `dl-action-btn ${btnClass}`;
        a.href = link;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.innerHTML = `<span>${icon}</span> <span>${escapeHtml(label)}</span>`;
        btnGrid.appendChild(a);

        // Copy button next to link
        const copyBtn = document.createElement("button");
        copyBtn.type = "button";
        copyBtn.className = "dl-action-btn dl-btn-copy";
        copyBtn.title = "Copy Download Link";
        copyBtn.innerHTML = `<span>📋</span> Copy`;
        copyBtn.addEventListener("click", () => copyToClipboard(link, `Copied: ${label} link`));
        btnGrid.appendChild(copyBtn);
      });

      card.appendChild(tierHeader);
      card.appendChild(btnGrid);
      DOM.modalDownloadTiers.appendChild(card);
    });
  }

  function renderRelatedMovies(related) {
    if (!DOM.modalRelatedGrid) return;
    DOM.modalRelatedGrid.replaceChildren();

    related.forEach((rel) => {
      const card = document.createElement("div");
      card.className = "related-card";
      card.innerHTML = `
        <img class="related-thumb" src="${escapeHtml(rel.thumbnail || FALLBACK_POSTER_SVG)}" alt="${escapeHtml(rel.title)}" loading="lazy" onerror="this.src='${FALLBACK_POSTER_SVG}'">
        <div class="related-info">
          <div class="related-title">${escapeHtml(rel.title)}</div>
          <div class="related-meta">${escapeHtml(rel.year || "")} ${rel.rating ? `• ★${rel.rating}` : ""}</div>
        </div>
      `;
      card.addEventListener("click", () => {
        openMovieDetails(rel.id);
        const topEl = document.querySelector("#movie-modal .modal-window");
        if (topEl) topEl.scrollTop = 0;
      });
      DOM.modalRelatedGrid.appendChild(card);
    });
  }

  function closeMovieDetails() {
    if (!DOM.movieModal) return;
    DOM.movieModal.close();
    state.activeMovieId = null;
    pushStateToUrl(true);
    if (DOM.modalTrailerEmbed) {
      DOM.modalTrailerEmbed.replaceChildren(); // Stop video audio
    }
  }

  // Screenshot Lightbox
  function openLightbox(imageUrl) {
    if (!DOM.lightboxModal || !DOM.lightboxImg) return;
    DOM.lightboxImg.src = imageUrl;
    DOM.lightboxModal.showModal();
  }

  function closeLightbox() {
    if (!DOM.lightboxModal) return;
    DOM.lightboxModal.close();
    DOM.lightboxImg.src = "";
  }

  // Mobile Drawer
  function openMobileDrawer() {
    DOM.mobileDrawer.classList.add("open");
    DOM.drawerBackdrop.classList.add("open");
    DOM.mobileDrawer.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
  }

  function closeMobileDrawer() {
    DOM.mobileDrawer.classList.remove("open");
    DOM.drawerBackdrop.classList.remove("open");
    DOM.mobileDrawer.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
  }

  // Real-time Search Autocomplete
  let suggestTimer;
  async function handleSearchInput(query) {
    query = query.trim();
    if (DOM.headerSearchClear) DOM.headerSearchClear.hidden = !query;

    if (query.length < 2) {
      DOM.searchSuggestions.hidden = true;
      return;
    }

    window.clearTimeout(suggestTimer);
    suggestTimer = window.setTimeout(async () => {
      try {
        const data = await getJson(`/api/suggest?q=${encodeURIComponent(query)}`);
        renderSearchSuggestions(data.results || []);
      } catch (e) {
        DOM.searchSuggestions.hidden = true;
      }
    }, 200);
  }

  function renderSearchSuggestions(results) {
    if (!DOM.searchSuggestions || !DOM.suggestionsList) return;
    if (results.length === 0) {
      DOM.searchSuggestions.hidden = true;
      return;
    }

    DOM.suggestionsList.replaceChildren();
    results.forEach((item) => {
      const el = document.createElement("div");
      el.className = "suggestion-item";
      el.innerHTML = `
        <img class="suggestion-thumb" src="${escapeHtml(item.thumbnail || FALLBACK_POSTER_SVG)}" alt="" onerror="this.src='${FALLBACK_POSTER_SVG}'">
        <div class="suggestion-info">
          <div class="suggestion-title">${escapeHtml(item.title)}</div>
          <div class="suggestion-meta">
            <span>${escapeHtml(item.year || "")}</span>
            ${item.rating ? `<span class="suggestion-badge">★ ${escapeHtml(item.rating)}</span>` : ""}
            <span>${escapeHtml(item.quality ? item.quality.split("|")[0] : "")}</span>
          </div>
        </div>
      `;
      el.addEventListener("click", () => {
        DOM.searchSuggestions.hidden = true;
        openMovieDetails(item.id);
      });
      DOM.suggestionsList.appendChild(el);
    });

    DOM.searchSuggestions.hidden = false;
  }

  // Event Listeners Initialization
  function initEvents() {
    // Header search
    if (DOM.headerSearchInput) {
      DOM.headerSearchInput.addEventListener("input", (e) => handleSearchInput(e.target.value));
      DOM.headerSearchInput.addEventListener("focus", (e) => {
        if (e.target.value.trim().length >= 2) handleSearchInput(e.target.value);
      });
    }

    if (DOM.headerSearchForm) {
      DOM.headerSearchForm.addEventListener("submit", (e) => {
        e.preventDefault();
        DOM.searchSuggestions.hidden = true;
        state.query = DOM.headerSearchInput.value.trim();
        state.page = 1;
        updateToolbarInputs();
        pushStateToUrl();
        loadMovies();
        scrollToGrid();
      });
    }

    if (DOM.headerSearchClear) {
      DOM.headerSearchClear.addEventListener("click", () => {
        DOM.headerSearchInput.value = "";
        DOM.headerSearchClear.hidden = true;
        DOM.searchSuggestions.hidden = true;
        state.query = "";
        state.page = 1;
        updateToolbarInputs();
        pushStateToUrl();
        loadMovies();
      });
    }

    // Close suggestions when clicking outside
    document.addEventListener("click", (e) => {
      if (DOM.searchSuggestions && !DOM.searchSuggestions.contains(e.target) && !DOM.headerSearchForm.contains(e.target)) {
        DOM.searchSuggestions.hidden = true;
      }
    });

    // Keyboard shortcut '/' to search
    document.addEventListener("keydown", (e) => {
      if (e.key === "/" && document.activeElement.tagName !== "INPUT" && document.activeElement.tagName !== "TEXTAREA") {
        e.preventDefault();
        if (DOM.headerSearchInput) DOM.headerSearchInput.focus();
      }
      if (e.key === "Escape") {
        if (!DOM.lightboxModal.hidden && DOM.lightboxModal.open) {
          closeLightbox();
        } else if (!DOM.movieModal.hidden && DOM.movieModal.open) {
          closeMovieDetails();
        } else if (!DOM.searchSuggestions.hidden) {
          DOM.searchSuggestions.hidden = true;
        }
      }
    });

    // Desktop Nav Category clicks
    if (DOM.desktopNav) {
      DOM.desktopNav.querySelectorAll("[data-category]").forEach((link) => {
        link.addEventListener("click", (e) => {
          e.preventDefault();
          state.category = link.dataset.category;
          state.page = 1;
          updateToolbarInputs();
          pushStateToUrl();
          loadMovies();
          scrollToGrid();
        });
      });

      // Desktop Genres Dropdown
      if (DOM.desktopGenresDropdown) {
        DOM.desktopGenresDropdown.querySelectorAll("[data-genre]").forEach((link) => {
          link.addEventListener("click", (e) => {
            e.preventDefault();
            state.genre = link.dataset.genre;
            state.page = 1;
            updateToolbarInputs();
            pushStateToUrl();
            loadMovies();
            scrollToGrid();
          });
        });
      }

      // Desktop Years Dropdown
      if (DOM.desktopYearsDropdown) {
        DOM.desktopYearsDropdown.querySelectorAll("[data-year]").forEach((link) => {
          link.addEventListener("click", (e) => {
            e.preventDefault();
            state.year = link.dataset.year;
            state.page = 1;
            updateToolbarInputs();
            pushStateToUrl();
            loadMovies();
            scrollToGrid();
          });
        });
      }
    }

    // Mobile Drawer
    if (DOM.menuToggle) DOM.menuToggle.addEventListener("click", openMobileDrawer);
    if (DOM.drawerClose) DOM.drawerClose.addEventListener("click", closeMobileDrawer);
    if (DOM.drawerBackdrop) DOM.drawerBackdrop.addEventListener("click", closeMobileDrawer);

    if (DOM.mobileDrawer) {
      DOM.mobileDrawer.querySelectorAll("[data-category]").forEach((link) => {
        link.addEventListener("click", (e) => {
          e.preventDefault();
          state.category = link.dataset.category;
          state.page = 1;
          closeMobileDrawer();
          updateToolbarInputs();
          pushStateToUrl();
          loadMovies();
          scrollToGrid();
        });
      });
    }

    // Category Quick Pills
    if (DOM.categoryPills) {
      DOM.categoryPills.querySelectorAll(".pill-chip").forEach((pill) => {
        pill.addEventListener("click", () => {
          if (pill.dataset.category) {
            state.category = pill.dataset.category;
          } else if (pill.dataset.quality) {
            state.quality = pill.dataset.quality;
          } else if (pill.dataset.genre) {
            state.genre = pill.dataset.genre;
          }
          state.page = 1;
          updateToolbarInputs();
          pushStateToUrl();
          loadMovies();
          scrollToGrid();
        });
      });
    }

    // Slider arrows
    if (DOM.prevSlideBtn) DOM.prevSlideBtn.addEventListener("click", () => goToSlide(state.currentSlide - 1));
    if (DOM.nextSlideBtn) DOM.nextSlideBtn.addEventListener("click", () => goToSlide(state.currentSlide + 1));

    // Filter toolbar controls
    let filterDebounce;
    if (DOM.filterSearchInput) {
      DOM.filterSearchInput.addEventListener("input", (e) => {
        window.clearTimeout(filterDebounce);
        filterDebounce = window.setTimeout(() => {
          state.query = e.target.value.trim();
          state.page = 1;
          updateToolbarInputs();
          pushStateToUrl();
          loadMovies();
        }, 300);
      });
    }

    if (DOM.categorySelect) {
      DOM.categorySelect.addEventListener("change", (e) => {
        state.category = e.target.value;
        state.page = 1;
        updateToolbarInputs();
        pushStateToUrl();
        loadMovies();
      });
    }

    if (DOM.languageSelect) {
      DOM.languageSelect.addEventListener("change", (e) => {
        state.language = e.target.value;
        state.page = 1;
        updateToolbarInputs();
        pushStateToUrl();
        loadMovies();
      });
    }

    if (DOM.genreSelect) {
      DOM.genreSelect.addEventListener("change", (e) => {
        state.genre = e.target.value;
        state.page = 1;
        updateToolbarInputs();
        pushStateToUrl();
        loadMovies();
      });
    }

    if (DOM.qualitySelect) {
      DOM.qualitySelect.addEventListener("change", (e) => {
        state.quality = e.target.value;
        state.page = 1;
        updateToolbarInputs();
        pushStateToUrl();
        loadMovies();
      });
    }

    if (DOM.yearSelect) {
      DOM.yearSelect.addEventListener("change", (e) => {
        state.year = e.target.value;
        state.page = 1;
        updateToolbarInputs();
        pushStateToUrl();
        loadMovies();
      });
    }

    if (DOM.sortSelect) {
      DOM.sortSelect.addEventListener("change", (e) => {
        state.sort = e.target.value;
        state.page = 1;
        updateToolbarInputs();
        pushStateToUrl();
        loadMovies();
      });
    }

    // Reset filters
    const handleReset = () => {
      state.query = "";
      state.category = "all";
      state.language = "";
      state.genre = "";
      state.quality = "";
      state.year = "";
      state.sort = "newest";
      state.page = 1;
      updateToolbarInputs();
      pushStateToUrl();
      loadMovies();
    };

    if (DOM.resetFiltersBtn) DOM.resetFiltersBtn.addEventListener("click", handleReset);
    if (DOM.clearAllTagsBtn) DOM.clearAllTagsBtn.addEventListener("click", handleReset);
    if (DOM.emptyResetBtn) DOM.emptyResetBtn.addEventListener("click", handleReset);

    if (DOM.emptyBrowseBtn) {
      DOM.emptyBrowseBtn.addEventListener("click", () => {
        handleReset();
        state.category = "bollywood";
        updateToolbarInputs();
        pushStateToUrl();
        loadMovies();
      });
    }

    // Status retry button
    if (DOM.statusRetryBtn) {
      DOM.statusRetryBtn.addEventListener("click", () => {
        clearError();
        loadMovies();
      });
    }

    // Page jump input
    if (DOM.pageJumpBtn && DOM.pageJumpInput) {
      const handleJump = () => {
        const val = parseInt(DOM.pageJumpInput.value, 10);
        if (!isNaN(val) && val >= 1 && val <= state.pages) {
          state.page = val;
          pushStateToUrl();
          loadMovies();
          scrollToGrid();
        } else {
          showToast(`Please enter a page between 1 and ${state.pages}`);
        }
      };
      DOM.pageJumpBtn.addEventListener("click", handleJump);
      DOM.pageJumpInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") handleJump();
      });
    }

    // Modal close handlers
    if (DOM.modalCloseBtn) DOM.modalCloseBtn.addEventListener("click", closeMovieDetails);
    if (DOM.modalBackdropClose) DOM.modalBackdropClose.addEventListener("click", closeMovieDetails);
    if (DOM.modalBcHome) {
      DOM.modalBcHome.addEventListener("click", (e) => {
        e.preventDefault();
        closeMovieDetails();
      });
    }

    // Lightbox close
    if (DOM.lightboxClose) DOM.lightboxClose.addEventListener("click", closeLightbox);
    if (DOM.lightboxModal) {
      DOM.lightboxModal.addEventListener("click", (e) => {
        if (e.target === DOM.lightboxModal) closeLightbox();
      });
    }

    // History popstate
    window.addEventListener("popstate", () => {
      syncStateFromUrl();
      loadMovies();
      if (state.activeMovieId) {
        openMovieDetails(state.activeMovieId);
      } else if (DOM.movieModal.open) {
        closeMovieDetails();
      }
    });

    // Refresh status stats periodically
    window.setInterval(async () => {
      try {
        const status = await getJson("/api/status");
        if (DOM.libraryStatusBadge) {
          DOM.libraryStatusBadge.textContent = `${formatNumber(status.total)} TITLES INDEXED`;
        }
        if (DOM.footerTotalCount) {
          DOM.footerTotalCount.textContent = `${formatNumber(status.total)}+`;
        }
        if (DOM.footerUpdatedAt && status.updated_at) {
          const d = new Date(status.updated_at * 1000);
          DOM.footerUpdatedAt.textContent = `Updated: ${d.toLocaleDateString()}`;
        }
      } catch (e) {
        // Silent fail for background poll
      }
    }, 30000);
  }

  // Application Bootstrap
  async function init() {
    if (DOM.lightboxModal && DOM.lightboxModal.open) DOM.lightboxModal.close();
    if (DOM.movieModal && DOM.movieModal.open) DOM.movieModal.close();
    if (DOM.toastNotification) DOM.toastNotification.hidden = true;

    syncStateFromUrl();
    initEvents();

    await loadFilters();
    loadFeatured();
    loadMovies();

    if (state.activeMovieId) {
      openMovieDetails(state.activeMovieId);
    }
  }

  // Run on DOM ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
