
import styled from 'styled-components';
import {theme} from "../styles/Theme.ts";

export const Surface = styled.div`
        box-sizing: border-box;

        width: 100%;
        max-width: 100%;
        min-width: 0;

        border-radius: 25px;

        background: linear-gradient(
            135deg,
            ${theme.colors.surface}E8,
            ${theme.colors.surface}B8
        );

        box-shadow:
            0 8px 24px rgba(24, 24, 36, 0.06),
            inset 0 2px 3px rgba(255, 255, 255, 0.85),
            inset 0 -2px 4px rgba(24, 24, 36, 0.04);

        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
`;
