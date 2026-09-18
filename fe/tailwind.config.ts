import type { Config } from 'tailwindcss'

/**
 * Tailwind v4 는 설정 파일 없이도 동작한다.
 * 이 파일은 팀 디자인 토큰(색·폰트 등)을 추가할 자리이며,
 * src/styles/index.css 의 @config 로 연결되어 있다.
 */
export default {
  theme: {
    extend: {},
  },
} satisfies Config
