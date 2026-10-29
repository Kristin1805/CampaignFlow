import {renderButton} from "../../components/buttons/button.js";
import {renderInput} from "../../components/inputs/input.js";

export function renderDashboardPage() {
    return `<h1>Dashboard</h1>` +
        renderButton('Add', 'primary') +
        renderButton('Today', 'secondary') +
        renderInput('email', 'Email', 'email', 'you@example.com')
}

