import styled from "styled-components";

interface StrategyLogoProps {
  className?: string
}

export function Logo({ className }: StrategyLogoProps) {
  return (
      <LogoImage
          src="/StrategyLab_logo_latest.svg"
          alt="StrategyLab"
          className={className}
          draggable={false}
      />
  )
}

const LogoImage = styled.img`
  display: block;
  width: 185px;
  height: auto;
  max-width: 100%;

  object-fit: contain;
  object-position: left center;

  user-select: none;

  @media (max-width: 720px) {
    width: 150px;
  }
`