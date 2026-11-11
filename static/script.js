async function loadLaws() {
	const response = await fetch("/laws/all", {
		method: "POST"
	});

	const laws = await response.json();

	const container = document.getElementById("law-books");
	container.innerHTML = "";

	for (const law of laws) {
		const element = document.createElement("div");
		element.classList.add("law-book");
		element.dataset.id = law.id;

		element.innerHTML = `
            <i class="fa-solid fa-${law.icon}"></i>
            <span>${law.abbr}</span>
        `;

		element.title = law.name;
		container.appendChild(element);
	}
}

loadLaws();

document.querySelectorAll(".paragraph").forEach((btn) => {
	btn.addEventListener("click", () => {
		const id = btn.dataset.id;
		window.location.href = `/law/${id}`;
	});
});

// search
const paragraphs = document.querySelectorAll(".paragraph");
const resultsLabel = document.querySelector("#search-results");
const searchInput = document.querySelector("#law-search");

if (searchInput) {
	const paragraphs = document.querySelectorAll(".paragraph");
	const resultsLabel = document.querySelector("#search-results");

	searchInput.addEventListener("input", () => {
		const query = searchInput.value.trim().toLowerCase();

		let count = 0;

		paragraphs.forEach((paragraph) => {
			const searchData = paragraph.dataset.search.toLowerCase();
			const matches = searchData.includes(query);

			paragraph.hidden = !matches;

			if (matches) count++;
		});

		if (resultsLabel) {
			resultsLabel.textContent = query ? `${count} Treffer` : "";
		}
	});
}

document.addEventListener("keydown", (event) => {
	if (
		event.key === "/" &&
		!["INPUT", "TEXTAREA"].includes(document.activeElement.tagName)
	) {
		event.preventDefault();
		searchInput.focus();
	}

	if (event.key === "Escape" && document.activeElement === searchInput) {
		searchInput.value = "";
		searchInput.dispatchEvent(new Event("input"));
		searchInput.blur();
	}
});
