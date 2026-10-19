import { html, nothing, render } from "lit";
import { HeadlessElement } from "../utils/element.js";
import {
  filterBookmarks,
  normalizeTag,
  normalizeUrl,
  titleFromUrl,
} from "../utils/onboarding.js";

const SAMPLE_URL = "https://en.wikipedia.org/wiki/World_Wide_Web";
const SAMPLE_TAGS = ["read-later", "learning", "reference"];
const SAMPLE_BOOKMARKS = [
  {
    title: "Homemade bread recipe",
    url: "https://example.com/bread-recipe",
    tags: ["cooking"],
  },
  {
    title: "Learning to code for beginners",
    url: "https://example.com/learn-to-code",
    tags: ["learning"],
  },
];

// Steps: 0 welcome, 1 save a link, 2 add a tag, 3 search, 4 done
const LAST_STEP = 4;
const TASK_COUNT = 3;

// Once the guide was completed or skipped, don't re-open it automatically
// again in this session, even if a cached page still says it should.
let completedInSession = false;

const checkIcon = html`
  <svg
    class="onb-check"
    width="18"
    height="18"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="2.5"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path d="M5 12.5l4.5 4.5L19 7.5"></path>
  </svg>
`;

class Onboarding extends HeadlessElement {
  init() {
    this.onKeyDown = this.onKeyDown.bind(this);
    this.teardown = this.teardown.bind(this);
    this.isOpen = false;

    if (this.dataset.autoOpen === "true" && !completedInSession) {
      this.open();
    }
  }

  disconnectedCallback() {
    this.teardown();
  }

  // Lifecycle

  open() {
    if (this.isOpen) {
      return;
    }
    this.isOpen = true;
    this.previousFocus = document.activeElement;
    this.state = {
      step: 0,
      url: "",
      urlError: "",
      bookmark: null,
      tagInput: "",
      query: "",
      searched: false,
    };

    this.className = "modal active onboarding";
    this.addEventListener("keydown", this.onKeyDown);
    document.addEventListener("turbo:before-cache", this.teardown);
    document.body.classList.add("scroll-lock");
    this.update();
    this.querySelector("[data-autofocus]")?.focus();
  }

  teardown() {
    if (!this.isOpen) {
      return;
    }
    this.isOpen = false;
    this.removeEventListener("keydown", this.onKeyDown);
    document.removeEventListener("turbo:before-cache", this.teardown);
    document.body.classList.remove("scroll-lock");
    render(nothing, this);
    this.className = "";
  }

  finish() {
    if (!completedInSession) {
      completedInSession = true;
      this.markCompleted();
    }
    const previousFocus = this.previousFocus;
    this.teardown();
    if (previousFocus && previousFocus.isConnected) {
      previousFocus.focus();
    }
  }

  markCompleted() {
    const url = this.dataset.completeUrl;
    if (!url) {
      return;
    }
    fetch(url, {
      method: "POST",
      headers: { "X-CSRFToken": this.dataset.csrfToken || "" },
      credentials: "same-origin",
    }).catch(() => {
      // Not critical: the guide may simply show up again on the next visit
      completedInSession = false;
    });
  }

  onKeyDown(event) {
    if (event.key === "Escape") {
      event.preventDefault();
      this.finish();
      return;
    }
    if (event.key === "Tab") {
      this.trapFocus(event);
    }
  }

  trapFocus(event) {
    const focusable = this.querySelectorAll(
      "a[href], button:not([disabled]), input:not([disabled])",
    );
    if (focusable.length === 0) {
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  // State

  setState(changes, { focus = false } = {}) {
    this.state = { ...this.state, ...changes };
    this.update();
    if (focus) {
      this.querySelector("[data-autofocus]")?.focus();
    }
  }

  goTo(step) {
    this.setState({ step }, { focus: true });
  }

  update() {
    render(this.renderDialog(), this);
  }

  isStepDone(step = this.state.step) {
    const { bookmark, searched } = this.state;
    switch (step) {
      case 1:
        return !!bookmark;
      case 2:
        return !!bookmark && bookmark.tags.length > 0;
      case 3:
        return searched;
      default:
        return true;
    }
  }

  // Actions

  saveUrl(event) {
    event.preventDefault();
    const href = normalizeUrl(this.state.url);
    if (!href) {
      this.setState({
        urlError: "That address does not look right. Try example.com/article.",
      });
      return;
    }
    this.setState({
      urlError: "",
      bookmark: { url: href, title: titleFromUrl(href), tags: [] },
    });
  }

  addTag(event, tag = this.state.tagInput) {
    event?.preventDefault();
    const name = normalizeTag(tag);
    const { bookmark } = this.state;
    if (!name || bookmark.tags.includes(name)) {
      this.setState({ tagInput: "" });
      return;
    }
    this.setState({
      tagInput: "",
      bookmark: { ...bookmark, tags: [...bookmark.tags, name] },
    });
  }

  setQuery(query) {
    const all = this.practiceBookmarks();
    const results = filterBookmarks(all, query);
    const narrowed = results.length > 0 && results.length < all.length;
    this.setState({
      query,
      searched: this.state.searched || (query.trim() !== "" && narrowed),
    });
  }

  practiceBookmarks() {
    return [this.state.bookmark, ...SAMPLE_BOOKMARKS].filter(Boolean);
  }

  openNewBookmark(event) {
    event.preventDefault();
    const href = event.currentTarget.getAttribute("href");
    this.finish();
    Turbo.visit(href);
  }

  // Rendering

  renderDialog() {
    const { step } = this.state;
    const progress = (step / LAST_STEP) * 100;

    return html`
      <div class="modal-overlay"></div>
      <div
        class="modal-container onb-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="onb-title"
      >
        <div
          class="onb-progress"
          role="progressbar"
          aria-valuemin="0"
          aria-valuemax=${LAST_STEP}
          aria-valuenow=${step}
          aria-label="Guide progress"
        >
          <div class="onb-progress-bar" style="width: ${progress}%"></div>
        </div>
        <div class="onb-body">${this.renderStep()}</div>
        ${this.renderFooter()}
      </div>
    `;
  }

  renderStep() {
    switch (this.state.step) {
      case 0:
        return this.renderWelcome();
      case 1:
        return this.renderSaveStep();
      case 2:
        return this.renderTagStep();
      case 3:
        return this.renderSearchStep();
      default:
        return this.renderDoneStep();
    }
  }

  renderFooter() {
    const { step } = this.state;
    const done = this.isStepDone();

    if (step === 0) {
      return html`
        <div class="onb-footer">
          <button type="button" class="onb-link" @click=${() => this.finish()}>
            Skip
          </button>
          <button
            type="button"
            class="onb-btn onb-btn-primary"
            data-autofocus
            @click=${() => this.goTo(1)}
          >
            Start
          </button>
        </div>
      `;
    }

    if (step === LAST_STEP) {
      return html`
        <div class="onb-footer">
          <button type="button" class="onb-link" @click=${() => this.finish()}>
            Later
          </button>
          <a
            class="onb-btn onb-btn-primary"
            href=${this.dataset.newUrl || "#"}
            data-autofocus
            @click=${(event) => this.openNewBookmark(event)}
          >
            Add a real bookmark
          </a>
        </div>
      `;
    }

    return html`
      <div class="onb-footer">
        <button
          type="button"
          class="onb-link"
          @click=${() => this.goTo(step - 1)}
        >
          Back
        </button>
        <div class="onb-footer-actions">
          <button type="button" class="onb-link" @click=${() => this.finish()}>
            Skip
          </button>
          <button
            type="button"
            class="onb-btn onb-btn-primary"
            ?disabled=${!done}
            @click=${() => this.goTo(step + 1)}
          >
            Continue
          </button>
        </div>
      </div>
    `;
  }

  renderTaskHeader(index, title) {
    return html`
      <p class="onb-eyebrow">Task ${index} / ${TASK_COUNT}</p>
      <h2 class="onb-title" id="onb-title">${title}</h2>
    `;
  }

  renderSuccess(message) {
    return html`
      <p class="onb-success" role="status">${checkIcon}<span>${message}</span></p>
    `;
  }

  renderBookmarkCard(bookmark, { highlight = false } = {}) {
    return html`
      <div class="onb-card ${highlight ? "onb-card-new" : ""}">
        <div class="onb-card-title">${bookmark.title}</div>
        <div class="onb-card-url">${bookmark.url}</div>
        ${bookmark.tags.length > 0
          ? html`
              <div class="onb-tags">
                ${bookmark.tags.map(
                  (tag) => html`<span class="onb-tag">#${tag}</span>`,
                )}
              </div>
            `
          : nothing}
      </div>
    `;
  }

  renderWelcome() {
    const principles = [
      ["Save fast", "One link, one click. No need to organise first."],
      [
        "Find it again",
        "Tags and search instead of nested folders.",
      ],
      [
        "Yours alone",
        "Your data belongs to you. You decide what to keep or share.",
      ],
    ];

    return html`
      <p class="onb-eyebrow">Welcome to linkding</p>
      <h2 class="onb-title" id="onb-title">
        A place to keep everything worth remembering that you find online.
      </h2>
      <p class="onb-text">
        Read a great article or found a useful tool, and a few weeks later you
        cannot remember where it was? linkding is a tidy drawer for those links,
        so you can always find them again.
      </p>
      <ul class="onb-principles">
        ${principles.map(
          ([name, text]) => html`
            <li>
              <strong>${name}</strong>
              <span>${text}</span>
            </li>
          `,
        )}
      </ul>
      <p class="onb-hint">
        It takes about 2 minutes. You will do 3 small tasks yourself. This is a
        practice area: nothing you do here is saved to your account.
      </p>
    `;
  }

  renderSaveStep() {
    const { url, urlError, bookmark } = this.state;

    return html`
      ${this.renderTaskHeader(1, "Save your first link")}
      <p class="onb-text">
        Paste the address of a web page into the box below and press Save.
        No link at hand? Use the sample link.
      </p>
      <form
        class="onb-row"
        data-turbo="false"
        novalidate
        @submit=${(event) => this.saveUrl(event)}
      >
        <input
          class="onb-input"
          type="text"
          inputmode="url"
          autocomplete="off"
          placeholder="example.com/article"
          aria-label="Web page address"
          data-autofocus
          .value=${url}
          @input=${(event) => this.setState({ url: event.target.value })}
        />
        <button type="submit" class="onb-btn onb-btn-primary">Save</button>
      </form>
      ${urlError ? html`<p class="onb-error" role="alert">${urlError}</p>` : nothing}
      ${!bookmark
        ? html`
            <button
              type="button"
              class="onb-chip"
              @click=${() => this.setState({ url: SAMPLE_URL, urlError: "" })}
            >
              Use the sample link
            </button>
          `
        : html`
            ${this.renderSuccess("Great! You just saved your first bookmark.")}
            ${this.renderBookmarkCard(bookmark, { highlight: true })}
          `}
      <p class="onb-hint">
        In the real app: press Add bookmark at the top right, paste the link
        and save.
      </p>
    `;
  }

  renderTagStep() {
    const { bookmark, tagInput } = this.state;
    const suggestions = SAMPLE_TAGS.filter((tag) => !bookmark.tags.includes(tag));

    return html`
      ${this.renderTaskHeader(2, "Tag it to find it")}
      <p class="onb-text">
        A tag is a short label that groups links on the same topic. Add a tag to
        the bookmark you just saved.
      </p>
      ${this.renderBookmarkCard(bookmark)}
      <form
        class="onb-row"
        data-turbo="false"
        novalidate
        @submit=${(event) => this.addTag(event)}
      >
        <input
          class="onb-input"
          type="text"
          autocomplete="off"
          placeholder="for example: read-later"
          aria-label="Tag name"
          data-autofocus
          .value=${tagInput}
          @input=${(event) => this.setState({ tagInput: event.target.value })}
        />
        <button type="submit" class="onb-btn onb-btn-primary">Add</button>
      </form>
      ${suggestions.length > 0
        ? html`
            <div class="onb-chips">
              ${suggestions.map(
                (tag) => html`
                  <button
                    type="button"
                    class="onb-chip"
                    @click=${() => this.addTag(null, tag)}
                  >
                    #${tag}
                  </button>
                `,
              )}
            </div>
          `
        : nothing}
      ${bookmark.tags.length > 0
        ? this.renderSuccess("Nice! A bookmark can have many tags.")
        : nothing}
    `;
  }

  renderSearchStep() {
    const { query, searched, bookmark } = this.state;
    const all = this.practiceBookmarks();
    const results = filterBookmarks(all, query);
    const tryTag = bookmark.tags[0];

    return html`
      ${this.renderTaskHeader(3, "Find it in a second")}
      <p class="onb-text">
        Now try to find it again. Type a few letters into the search box, for
        example the tag you just created. The list narrows as you type.
      </p>
      <input
        class="onb-input"
        type="search"
        autocomplete="off"
        placeholder="Search by title, link or tag"
        aria-label="Search"
        data-autofocus
        .value=${query}
        @input=${(event) => this.setQuery(event.target.value)}
      />
      ${tryTag && !searched
        ? html`
            <div class="onb-chips">
              <button
                type="button"
                class="onb-chip"
                @click=${() => this.setQuery(tryTag)}
              >
                Try: ${tryTag}
              </button>
            </div>
          `
        : nothing}
      <div class="onb-results" aria-live="polite">
        ${results.length > 0
          ? results.map((item) => this.renderBookmarkCard(item))
          : html`<p class="onb-empty">No results. Try another word.</p>`}
      </div>
      ${searched
        ? this.renderSuccess("That's it! You found your link again.")
        : nothing}
    `;
  }

  renderDoneStep() {
    const achievements = [
      "Saved a link",
      "Tagged the link",
      "Found the link with the search box",
    ];

    return html`
      <p class="onb-eyebrow">Done</p>
      <h2 class="onb-title" id="onb-title">You are ready.</h2>
      <ul class="onb-achievements">
        ${achievements.map((text) => html`<li>${checkIcon}<span>${text}</span></li>`)}
      </ul>
      <p class="onb-text">
        The next step is simple: save a real link you want to read later. You
        will see it appear in the list right away.
      </p>
      <p class="onb-hint">
        Tip: install the browser extension from Settings, Integrations, to save
        a link with a single click. To see this guide again, press Guide in the
        menu bar.
      </p>
    `;
  }
}

customElements.define("ld-onboarding", Onboarding);

// Any element with this attribute re-opens the guide
document.addEventListener("click", (event) => {
  const trigger = event.target.closest?.("[data-onboarding-open]");
  if (!trigger) {
    return;
  }
  event.preventDefault();
  document.querySelector("ld-onboarding")?.open();
});
