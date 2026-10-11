import { html, nothing, render } from "lit";
import { HeadlessElement } from "../utils/element.js";
import {
  filterBookmarks,
  normalizeTag,
  normalizeUrl,
  titleFromUrl,
} from "../utils/onboarding.js";

const SAMPLE_URL = "https://vi.wikipedia.org/wiki/World_Wide_Web";
const SAMPLE_TAGS = ["đọc-sau", "học-tập", "tham-khảo"];
const SAMPLE_BOOKMARKS = [
  {
    title: "Công thức bánh mì làm tại nhà",
    url: "https://example.com/cong-thuc-banh-mi",
    tags: ["nấu-ăn"],
  },
  {
    title: "Cách học lập trình cho người mới",
    url: "https://example.com/hoc-lap-trinh",
    tags: ["học-tập"],
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
        urlError: "Địa chỉ này chưa đúng. Thử dạng example.com/bai-viet nhé.",
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
          aria-label="Tiến độ hướng dẫn"
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
            Bỏ qua
          </button>
          <button
            type="button"
            class="onb-btn onb-btn-primary"
            data-autofocus
            @click=${() => this.goTo(1)}
          >
            Bắt đầu
          </button>
        </div>
      `;
    }

    if (step === LAST_STEP) {
      return html`
        <div class="onb-footer">
          <button type="button" class="onb-link" @click=${() => this.finish()}>
            Để sau
          </button>
          <a
            class="onb-btn onb-btn-primary"
            href=${this.dataset.newUrl || "#"}
            data-autofocus
            @click=${(event) => this.openNewBookmark(event)}
          >
            Thêm bookmark thật
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
          Quay lại
        </button>
        <div class="onb-footer-actions">
          <button type="button" class="onb-link" @click=${() => this.finish()}>
            Bỏ qua
          </button>
          <button
            type="button"
            class="onb-btn onb-btn-primary"
            ?disabled=${!done}
            @click=${() => this.goTo(step + 1)}
          >
            Tiếp tục
          </button>
        </div>
      </div>
    `;
  }

  renderTaskHeader(index, title) {
    return html`
      <p class="onb-eyebrow">Việc ${index} / ${TASK_COUNT}</p>
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
      ["Lưu nhanh", "Một đường link, một cú bấm. Không cần sắp xếp trước."],
      [
        "Tìm lại dễ",
        "Gắn tag và tìm kiếm thay cho những thư mục lồng nhau.",
      ],
      [
        "Của riêng bạn",
        "Dữ liệu thuộc về bạn. Bạn quyết định giữ riêng hay chia sẻ.",
      ],
    ];

    return html`
      <p class="onb-eyebrow">Chào mừng bạn đến với linkding</p>
      <h2 class="onb-title" id="onb-title">
        Nơi giữ lại mọi thứ đáng nhớ bạn gặp trên mạng.
      </h2>
      <p class="onb-text">
        Đọc được một bài hay, thấy một công cụ hữu ích, rồi vài tuần sau không
        nhớ nó ở đâu? linkding là một ngăn kéo gọn gàng cho những đường link đó,
        để bạn luôn tìm lại được.
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
        Mất khoảng 2 phút. Bạn sẽ tự tay làm 3 việc nhỏ. Đây là khu thực hành,
        những gì bạn làm ở đây chưa được lưu vào tài khoản.
      </p>
    `;
  }

  renderSaveStep() {
    const { url, urlError, bookmark } = this.state;

    return html`
      ${this.renderTaskHeader(1, "Lưu link đầu tiên")}
      <p class="onb-text">
        Dán địa chỉ một trang web vào ô bên dưới rồi bấm Lưu. Chưa có link nào?
        Dùng link mẫu.
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
          placeholder="example.com/bai-viet"
          aria-label="Địa chỉ trang web"
          data-autofocus
          .value=${url}
          @input=${(event) => this.setState({ url: event.target.value })}
        />
        <button type="submit" class="onb-btn onb-btn-primary">Lưu</button>
      </form>
      ${urlError ? html`<p class="onb-error" role="alert">${urlError}</p>` : nothing}
      ${!bookmark
        ? html`
            <button
              type="button"
              class="onb-chip"
              @click=${() => this.setState({ url: SAMPLE_URL, urlError: "" })}
            >
              Dùng link mẫu
            </button>
          `
        : html`
            ${this.renderSuccess("Tuyệt! Bạn vừa lưu bookmark đầu tiên.")}
            ${this.renderBookmarkCard(bookmark, { highlight: true })}
          `}
      <p class="onb-hint">
        Trong app thật: bấm Add bookmark ở góc trên bên phải, dán link và lưu.
      </p>
    `;
  }

  renderTagStep() {
    const { bookmark, tagInput } = this.state;
    const suggestions = SAMPLE_TAGS.filter((tag) => !bookmark.tags.includes(tag));

    return html`
      ${this.renderTaskHeader(2, "Gắn tag để dễ tìm")}
      <p class="onb-text">
        Tag là nhãn ngắn giúp gom các link cùng chủ đề. Thêm một tag cho
        bookmark vừa lưu.
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
          placeholder="ví dụ: đọc-sau"
          aria-label="Tên tag"
          data-autofocus
          .value=${tagInput}
          @input=${(event) => this.setState({ tagInput: event.target.value })}
        />
        <button type="submit" class="onb-btn onb-btn-primary">Thêm</button>
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
        ? this.renderSuccess("Hay quá! Một bookmark có thể có nhiều tag.")
        : nothing}
    `;
  }

  renderSearchStep() {
    const { query, searched, bookmark } = this.state;
    const all = this.practiceBookmarks();
    const results = filterBookmarks(all, query);
    const tryTag = bookmark.tags[0];

    return html`
      ${this.renderTaskHeader(3, "Tìm lại trong tích tắc")}
      <p class="onb-text">
        Bây giờ thử tìm lại. Gõ vài chữ vào ô tìm kiếm, ví dụ tag bạn vừa tạo.
        Danh sách sẽ thu hẹp ngay khi bạn gõ.
      </p>
      <input
        class="onb-input"
        type="search"
        autocomplete="off"
        placeholder="Tìm theo tiêu đề, link hoặc tag"
        aria-label="Tìm kiếm"
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
                Thử: ${tryTag}
              </button>
            </div>
          `
        : nothing}
      <div class="onb-results" aria-live="polite">
        ${results.length > 0
          ? results.map((item) => this.renderBookmarkCard(item))
          : html`<p class="onb-empty">Không có kết quả. Thử từ khoá khác.</p>`}
      </div>
      ${searched
        ? this.renderSuccess("Đúng rồi! Bạn đã tìm lại được link của mình.")
        : nothing}
    `;
  }

  renderDoneStep() {
    const achievements = [
      "Lưu một link",
      "Gắn tag cho link",
      "Tìm lại link bằng ô tìm kiếm",
    ];

    return html`
      <p class="onb-eyebrow">Hoàn thành</p>
      <h2 class="onb-title" id="onb-title">Bạn đã sẵn sàng.</h2>
      <ul class="onb-achievements">
        ${achievements.map((text) => html`<li>${checkIcon}<span>${text}</span></li>`)}
      </ul>
      <p class="onb-text">
        Bước tiếp theo rất đơn giản: lưu một link thật mà bạn đang muốn đọc sau.
        Bạn sẽ thấy nó xuất hiện ngay trong danh sách.
      </p>
      <p class="onb-hint">
        Mẹo: cài tiện ích trình duyệt trong Settings, mục Integrations, để lưu
        link chỉ bằng một cú bấm. Muốn xem lại hướng dẫn này, bấm Hướng dẫn trên
        thanh menu.
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
