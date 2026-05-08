"use server";

import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

// Server Action: kaldes når login-formen submittes.
// Returnerer null ved succes (efter redirect), eller fejlbesked.
export async function login(formData: FormData) {
  const email = (formData.get("email") as string)?.trim();
  const password = formData.get("password") as string;

  if (!email || !password) {
    return { error: "Udfyld både email og adgangskode." };
  }

  const supabase = await createClient();
  const { error } = await supabase.auth.signInWithPassword({
    email,
    password,
  });

  if (error) {
    // Supabase returnerer engelske fejlbeskeder — oversæt de mest
    // almindelige til dansk for vores brugere.
    const dansk =
      error.message === "Invalid login credentials"
        ? "Forkert email eller adgangskode."
        : error.message;
    return { error: dansk };
  }

  // Succes: redirect til forsiden. redirect() kaster en speciel
  // exception som Next.js fanger — derfor ingen 'return' efter.
  redirect("/");
}

export async function logout() {
  const supabase = await createClient();
  await supabase.auth.signOut();
  redirect("/login");
}
