export function renderInput(id, label, type, placeholder){
    return `<label for="${id}">${label}</label>` +
        `<input type="${type}" name="${id}" id="${id}" class="input" placeholder="${placeholder}"/>`;
}