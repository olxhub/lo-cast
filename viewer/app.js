(() => {
  "use strict";

  const catalog = window.AVATAR_CATALOG;
  if (!catalog) {
    document.body.textContent = "The avatar catalog could not be loaded.";
    return;
  }

  const identities = [...catalog.identities].sort((left, right) => (
    left.name.localeCompare(right.name)
  ));
  const states = catalog.states;
  const images = catalog.images;
  const identitiesById = new Map(identities.map((item) => [item.id, item]));
  const statesById = new Map(states.map((item) => [item.id, item]));
  const identitiesByLowerId = new Map(
    identities.map((item) => [item.id.toLowerCase(), item.id]),
  );
  const statesByLowerId = new Map(
    states.map((item) => [item.id.toLowerCase(), item.id]),
  );
  const stateFallbacks = catalog.stateFallbacks || {};
  const stateFallbacksByLowerId = new Map(
    Object.entries(stateFallbacks).map(([source, target]) => [source.toLowerCase(), target]),
  );
  const identityOrder = new Map(identities.map((item, index) => [item.id, index]));
  const stateOrder = new Map(states.map((item, index) => [item.id, index]));
  const imagesByPerson = new Map(identities.map((item) => [item.id, []]));
  const imagesByState = new Map(states.map((item) => [item.id, []]));
  for (const item of images) {
    imagesByPerson.get(item.identity).push(item);
    if (!item.variant) imagesByState.get(item.state).push(item);
  }
  for (const items of imagesByPerson.values()) {
    items.sort((left, right) => {
      const stateDifference = stateOrder.get(left.state) - stateOrder.get(right.state);
      if (stateDifference) return stateDifference;
      if (!left.variant) return -1;
      if (!right.variant) return 1;
      return left.variant.localeCompare(right.variant);
    });
  }
  for (const items of imagesByState.values()) {
    items.sort((left, right) => (
      identityOrder.get(left.identity) - identityOrder.get(right.identity)
    ));
  }
  const params = new URLSearchParams(window.location.search);

  function resolveIdentity(value) {
    if (!value) return null;
    return identitiesById.has(value) ? value : identitiesByLowerId.get(value.toLowerCase());
  }

  function resolveState(value) {
    if (!value) return null;
    if (statesById.has(value)) return value;
    const normalized = value.toLowerCase();
    if (statesByLowerId.has(normalized)) return statesByLowerId.get(normalized);
    return stateFallbacksByLowerId.get(normalized) || null;
  }

  let view = params.get("view") === "state" || (!params.has("view") && params.has("state"))
    ? "state"
    : "person";
  let selectedPerson = resolveIdentity(params.get("person")) || identities[0].id;
  let selectedState = resolveState(params.get("state"))
    || (statesById.has("calm") ? "calm" : states[0].id);

  const elements = {
    viewButtons: [...document.querySelectorAll("[data-view]")],
    primarySelect: document.querySelector("#primary-select"),
    title: document.querySelector("#grid-title"),
    grid: document.querySelector("#avatar-grid"),
  };

  function words(value) {
    return value
      .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
      .replace(/[-_]+/g, " ")
      .replace(/^./, (letter) => letter.toUpperCase());
  }

  function stateLabel(stateId, variant) {
    return variant ? `${words(stateId)} — ${words(variant)}` : words(stateId);
  }

  function avatarUrl(file) {
    return new URL(`../avatars/${file}`, window.location.href).href;
  }

  function updateUrl() {
    const next = new URL(window.location.href);
    next.searchParams.set("view", view);
    next.searchParams.set("person", selectedPerson);
    next.searchParams.set("state", selectedState);
    next.searchParams.delete("variant");
    window.history.replaceState(null, "", next);
  }

  function populateSelect() {
    const items = view === "person" ? identities : states;
    const selected = view === "person" ? selectedPerson : selectedState;
    elements.primarySelect.replaceChildren();
    for (const item of items) {
      const option = document.createElement("option");
      option.value = item.id;
      option.textContent = view === "person" ? item.name : words(item.id);
      elements.primarySelect.append(option);
    }
    elements.primarySelect.value = selected;
  }

  function createCard(item) {
    const person = identitiesById.get(item.identity);
    const state = statesById.get(item.state);
    const card = document.createElement("button");
    card.type = "button";
    card.className = "avatar-card";

    const image = document.createElement("img");
    image.src = avatarUrl(item.file);
    image.alt = `${person.name}: ${stateLabel(state.id, item.variant)}`;
    image.loading = "lazy";
    image.decoding = "async";
    image.addEventListener("error", () => card.classList.add("image-missing"));

    const caption = document.createElement("span");
    caption.className = "avatar-caption";
    caption.textContent = view === "person"
      ? stateLabel(state.id, item.variant)
      : person.name;
    card.append(image, caption);
    card.addEventListener("click", () => {
      if (view === "person") {
        selectedState = state.id;
      }
      else selectedPerson = person.id;
      view = view === "person" ? "state" : "person";
      render();
      window.scrollTo({ top: 0, behavior: "auto" });
    });
    return card;
  }

  function renderGrid() {
    const items = view === "person"
      ? imagesByPerson.get(selectedPerson)
      : imagesByState.get(selectedState);
    elements.grid.replaceChildren(...items.map(createCard));
  }

  function render() {
    const person = identitiesById.get(selectedPerson);
    const state = statesById.get(selectedState);
    for (const button of elements.viewButtons) {
      button.setAttribute("aria-pressed", String(button.dataset.view === view));
    }
    elements.primarySelect.setAttribute("aria-label", view === "person" ? "Person" : "State");
    elements.title.textContent = view === "person"
      ? person.name
      : words(state.id);
    populateSelect();
    renderGrid();
    updateUrl();
  }

  elements.viewButtons.forEach((button) => {
    button.addEventListener("click", () => {
      view = button.dataset.view;
      render();
    });
  });
  elements.primarySelect.addEventListener("change", () => {
    if (view === "person") selectedPerson = elements.primarySelect.value;
    else selectedState = elements.primarySelect.value;
    render();
  });
  render();
})();
