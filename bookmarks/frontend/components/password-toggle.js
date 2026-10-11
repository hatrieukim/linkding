import { HeadlessElement } from "../utils/element";

class PasswordToggle extends HeadlessElement {
  init() {
    this.input = this.querySelector("input");
    this.button = this.querySelector("button");
    if (!this.input || !this.button) {
      console.error("Password toggle requires an input and a button");
      return;
    }
    this.toggle = this.toggle.bind(this);
    this.button.addEventListener("click", this.toggle);
    // Always start with the password hidden, also when restored from cache
    this.update(false);
  }

  toggle() {
    this.update(this.input.type === "password");
  }

  update(visible) {
    this.input.type = visible ? "text" : "password";
    this.button.setAttribute(
      "aria-label",
      visible ? "Hide password" : "Show password",
    );
    this.button.querySelector(".icon-show").hidden = visible;
    this.button.querySelector(".icon-hide").hidden = !visible;
  }
}

customElements.define("ld-password-toggle", PasswordToggle);
