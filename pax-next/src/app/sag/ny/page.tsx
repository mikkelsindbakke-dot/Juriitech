import { redirect } from "next/navigation";

// Ny-sag-flowet er flyttet til forsiden. Behold redirect så gamle
// bogmærker og links stadig lander det rigtige sted.
export default function NySagPage() {
  redirect("/");
}
