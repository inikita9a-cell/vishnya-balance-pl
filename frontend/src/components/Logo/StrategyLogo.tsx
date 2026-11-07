
import { LogoImage } from "./Logo_Styles.ts"

interface StrategyLogoProps {
    className?: string
}

export function StrategyLogo({ className }: StrategyLogoProps) {
    return (
        <LogoImage
            src="/StrategyLab_logo_latest.svg"
            alt="StrategyLab"
            className={className}
            draggable={false}
        />
    )
}
