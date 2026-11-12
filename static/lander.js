(() => {
	"use strict";

	const searchInput = document.getElementById("global-search");
	const resultsSection = document.getElementById("search-results");
	const resultsList = document.getElementById("results-list");
	const resultsCount = document.getElementById("results-count");
	const loadMoreButton = document.getElementById("load-more");
	const searchStatus = document.getElementById("search-status");

	const PAGE_SIZE = 150;
	const SEARCH_ENDPOINT = "/laws/search/global/title";

	let currentQuery = "";
	let currentPage = 1;
	let totalResults = 0;
	let debounceTimeout = null;
	let activeController = null;
	let isLoading = false;

	function clearResults() {
		resultsList.replaceChildren();
		resultsCount.textContent = "";
		loadMoreButton.hidden = true;
		searchStatus.textContent = "";
	}

	function createResultElement(result) {
		const article = document.createElement("button");
		article.className = "search-result";

		const heading = document.createElement("h3");

		const prefix = result.no_prefix ? "" : result.prefix + " ";
		heading.textContent = `${prefix}${result.nr}`;

		if (result.name) {
			heading.textContent += ` - ${result.name}`;
		}

		const book = document.createElement("span");
		book.className = "search-result-book";
		book.textContent = `${result.book.abbr} · ${result.book.name}`;

		article.append(heading, book);

		article.addEventListener("click", () => {
			window.location.href = `/law/${result.id}`;
		});

		return article;
	}

	function updateResultsCount() {
		resultsCount.textContent = `${resultsList.children.length} von ${totalResults} Ergebnissen`;
	}

	async function search(query, page = 1) {
		if (isLoading) return;

		if (activeController) {
			activeController.abort();
		}

		const controller = new AbortController();
		activeController = controller;
		isLoading = true;

		searchStatus.textContent = "Suche läuft …";
		loadMoreButton.disabled = true;

		try {
			const response = await fetch(SEARCH_ENDPOINT, {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
				},
				body: JSON.stringify({
					query,
					page,
					limit: PAGE_SIZE,
				}),
				signal: controller.signal,
			});

			if (!response.ok) {
				throw new Error(`HTTP ${response.status}`);
			}

			const data = await response.json();

			// Veraltete Suchanfragen ignorieren
			if (query !== currentQuery) return;

			if (page === 1) {
				resultsList.replaceChildren();
			}

			totalResults = data.total;

			for (const result of data.results) {
				resultsList.appendChild(createResultElement(result));
			}

			currentPage = data.page;

			updateResultsCount();

			loadMoreButton.hidden = !data.has_more;
			searchStatus.textContent =
				data.total === 0 ? "Keine Ergebnisse gefunden." : "";
		} catch (error) {
			if (error.name !== "AbortError") {
				console.error("Search failed:", error);
				searchStatus.textContent =
					"Bei der Suche ist ein Fehler aufgetreten.";
			}
		} finally {
			if (activeController === controller) {
				activeController = null;
				isLoading = false;
				loadMoreButton.disabled = false;
			}
		}
	}

	// Live-Suche mit Debouncing
	searchInput.addEventListener("input", () => {
		clearTimeout(debounceTimeout);

		const query = searchInput.value.trim();

		currentQuery = query;
		currentPage = 1;

		if (activeController) {
			activeController.abort();
			activeController = null;
			isLoading = false;
		}

		clearResults();

		if (!query) {
			resultsSection.hidden = true;
			return;
		}

		resultsSection.hidden = false;

		debounceTimeout = setTimeout(() => {
			search(query, 1);
		}, 300);
	});

	// Weitere Ergebnisse laden
	loadMoreButton.addEventListener("click", () => {
		if (currentQuery && !isLoading) {
			search(currentQuery, currentPage + 1);
		}
	});
})();
