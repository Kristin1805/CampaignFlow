import {renderButton} from "../../components/buttons/button.js";

export function renderDashboardPage() {
    return `<h1>Dashboard</h1>` + renderButton('Add', 'primary') + renderButton('Today', 'secondary');
}

