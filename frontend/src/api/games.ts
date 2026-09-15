import { http } from './client'
import type { CreateGameRequest, GameDTO } from '../types/api'

const games = (sessionId: string) => `/games/${sessionId}`

export const createGame = (data: CreateGameRequest = {}) =>
  http.post<GameDTO>('/games', data).then((r) => r.data)

export const getGame = (sessionId: string) =>
  http.get<GameDTO>(games(sessionId)).then((r) => r.data)

export const askQuestion = (sessionId: string, text: string) =>
  http.post<GameDTO>(`${games(sessionId)}/questions`, { text }).then((r) => r.data)

export const makeGuess = (sessionId: string, text: string) =>
  http.post<GameDTO>(`${games(sessionId)}/guesses`, { text }).then((r) => r.data)

export const skipPhase = (
  sessionId: string,
  currentPhase: 'question' | 'guess',
) =>
  http
    .post<GameDTO>(`${games(sessionId)}/skip`, { current_phase: currentPhase })
    .then((r) => r.data)

export const retry = (sessionId: string) =>
  http.post<GameDTO>(`${games(sessionId)}/retry`, {}).then((r) => r.data)

export const abandon = (sessionId: string) =>
  http.post<GameDTO>(`${games(sessionId)}/abandon`, {}).then((r) => r.data)
