import axios from "axios";


const api = axios.create({
  baseURL: "http://localhost:8003",
  timeout: 3000,
});


export async function getHealth(options = {}) {
  const response = await api.get("/health", options);
  return response.data;
}
