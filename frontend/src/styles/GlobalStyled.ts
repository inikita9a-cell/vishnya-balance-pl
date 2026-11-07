
import { createGlobalStyle } from "styled-components";
import { theme } from "./Theme";

export const GlobalStyle = createGlobalStyle`
    *,
    *::before,
    *::after {
        margin: 0;
        padding: 0;
        box-sizing: border-box;
    }

    html {
        scroll-behavior: smooth;
    }

    body {
        min-width: 320px;
        min-height: 100vh;

        background-color: ${theme.colors.bgColor};
        color: ${theme.colors.fontDark};

        font-family: ${theme.fonts.primary};
        font-weight: 400;
        -webkit-font-smoothing: antialiased;
    }

    h1, h2, h3 {
        font-family: ${theme.fonts.heading};
        font-weight: 600;
    }

    h4, h5, h6 {
        font-family: ${theme.fonts.primary};
        font-weight: 600;
    }

    p {
        font-family: inherit;
        font-size: 18px;
        font-weight: 500;
        line-height: 1.5;
    }

    button,
    input,
    select,
    textarea {
        font-family: ${theme.fonts.interface};
    }

    a {
        color: inherit;
        text-decoration: none;
    }

    ul, ol {
        list-style: none;
    }

    section, footer {
        background-color: ${theme.colors.bgColor};
    }
`;
