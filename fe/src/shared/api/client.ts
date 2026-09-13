// 모든 API 호출은 이 파일을 통과한다. fetch를 직접 부르는 곳은 여기뿐이어야 한다.



// export async function apiGet<T>(path: string): Promise<T> {
//   const res = await fetch(`${import.meta.env.VITE_API_BASE_URL}${path}`, {
//     headers: { Authorization: `Bearer ${getToken()}` },
//   })
//   if (!res.ok) throw await toApiError(res)
//   return res.json()
// }
