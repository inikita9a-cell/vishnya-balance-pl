import { useState, type FormEvent } from 'react';
import styled from 'styled-components';
import { post, message } from '../../api/client';
import type { User } from '../../api/types';
import { Field, PrimaryButton, ErrorBox } from '../../components/Ui';

type LoginProps = {
  onLogin: (user: User) => void;
};

export function Login({ onLogin }: LoginProps) {
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError('');

    try {
      onLogin(await post<User>('/login', { name: name.trim() }));
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }

  return (
      <Screen>
        <Card>
          <BrandLogo src="/StrategyLab_logo_latest.svg" alt="StrategyLab" />
          <Eyebrow>Аналитическая платформа</Eyebrow>
          <h1>
            Работайте с решениями,<br />а не с догадками.
          </h1>
          <p>
            Сравнивайте версии стратегий, исследуйте изменения и сохраняйте
            историю запусков в одном пространстве.
          </p>

          <form onSubmit={submit}>
            <label htmlFor="username">Ваше имя</label>
            <Field
                id="username"
                autoComplete="name"
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="Например, Аналитик"
                required
                maxLength={64}
            />
            {error && <ErrorBox role="alert">{error}</ErrorBox>}
            <PrimaryButton type="submit" disabled={busy || !name.trim()}>
              {busy ? 'Выполняется вход…' : 'Войти в StrategyLab'}
            </PrimaryButton>
          </form>

          <Small>Демонстрационный вход без пароля</Small>
        </Card>

        <Decor aria-hidden="true" />
      </Screen>
  );
}

const Screen = styled.main`
  min-height: 100vh;
  min-height: 100dvh;
  display: grid;
  grid-template-columns: minmax(420px, 55%) minmax(0, 1fr);
  background: #f7f7f9;

  @media (max-width: 850px) {
    grid-template-columns: 1fr;
  }
`;

const Card = styled.div`
  max-width: 560px;
  width: 100%;
  margin: auto;
  padding: 45px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;

  h1 {
    font-size: 29px;
    line-height: 1.3;
    margin: 30px 0 16px;
    letter-spacing: -1px;
  }

  p {
    font-size: 14px;
    color: #777783;
    line-height: 1.8;
    font-weight: 400;
    max-width: 420px;
  }

  form {
    margin-top: 40px;
    width: 100%;
    max-width: 390px;
    display: flex;
    flex-direction: column;
    gap: 13px;
  }

  label {
    font-size: 12px;
    font-weight: 750;
  }

  button {
    margin-top: 8px;
    min-height: 47px;
  }

  @media (max-width: 560px) {
    padding: 25px;

    h1 {
      font-size: 23px;
    }
  }
`;

const BrandLogo = styled.img`
  display: block;
  width: 225px;
  max-width: 100%;
  height: auto;
`;

const Eyebrow = styled.span`
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.015em;
  color: #8e8d98;
  margin-top: 28px;
`;

const Small = styled.span`
  font-size: 11px;
  color: #9999a2;
  margin-top: 36px;
`;

const Decor = styled.aside`
  position: relative;
  overflow: hidden;
  isolation: isolate;
  background:
      radial-gradient(ellipse 65% 55% at 95% 18%, rgba(244, 91, 61, 0.11), transparent 72%),
      radial-gradient(ellipse 75% 65% at 6% 93%, rgba(141, 127, 173, 0.14), transparent 74%),
      linear-gradient(145deg, #1c1c28 0%, #15151f 72%, #1b1a25 100%);

  &::before {
    content: '';
    position: absolute;
    inset: -30%;
    pointer-events: none;
    background: linear-gradient(
        117deg,
        transparent 35%,
        rgba(255, 255, 255, 0.012) 43%,
        rgba(255, 255, 255, 0.085) 49%,
        rgba(255, 255, 255, 0.012) 55%,
        transparent 63%
    );
    filter: blur(28px);
  }

  &::after {
    content: '';
    position: absolute;
    width: 440px;
    height: 440px;
    right: -235px;
    bottom: 5%;
    border-radius: 50%;
    pointer-events: none;
    background: radial-gradient(
        circle,
        rgba(244, 91, 61, 0.13) 0%,
        rgba(244, 91, 61, 0.035) 44%,
        transparent 72%
    );
    filter: blur(24px);
  }

  @media (max-width: 850px) {
    display: none;
  }
`;
