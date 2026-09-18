import { redirect } from "next/navigation";

import { homePath } from "@/lib/flags";

export default function HomePage() {
  redirect(homePath());
}
