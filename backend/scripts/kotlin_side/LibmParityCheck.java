// SPDX-License-Identifier: AGPL-3.0-only
//
// The JVM half of Phase W1's libm-parity measurement, and the executable form of the spec in
// ../measure_libm_parity_kotlin_side.md.
//
// Reads an artifact from `measure_libm_parity.py`, evaluates StrictMath.exp/log on each recorded
// input and compares to the `numpy` column BIT FOR BIT. StrictMath is fdlibm, identical on every JVM
// and CPU, so a clean run means the Kotlin port can call it and reproduce the Python reference.
//
// Java, not Kotlin, so it runs with nothing but a JDK:
//   java LibmParityCheck.java ../artifacts/libm-parity-sample.tsv
//
// Exit 0 = every row matched. 1 = a mismatch (first 20 printed). 2 = the artifact is unreadable.

import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.LinkedHashMap;
import java.util.Map;

public final class LibmParityCheck {

    private static final int PRINT_LIMIT = 20;

    /** Per-function tally: rows, mismatches, and the digest of the StrictMath stream. */
    private static final class Tally {
        long rows;
        long mismatches;
        long libmMismatches;
        double maxUlpError;
        String worstInput = "-";
        final MessageDigest inputDigest;
        final MessageDigest outputDigest;

        Tally() throws NoSuchAlgorithmException {
            inputDigest = MessageDigest.getInstance("SHA-256");
            outputDigest = MessageDigest.getInstance("SHA-256");
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("usage: java LibmParityCheck.java <artifact.tsv>");
            System.exit(2);
        }
        Path path = Path.of(args[0]);
        if (!Files.isReadable(path)) {
            System.err.println("cannot read artifact: " + path);
            System.exit(2);
        }

        Map<String, Tally> tallies = new LinkedHashMap<>();
        int printed = 0;

        try (BufferedReader in = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
            String line;
            while ((line = in.readLine()) != null) {
                if (line.isEmpty() || line.charAt(0) == '#' || line.startsWith("fn\t")) {
                    continue;
                }
                String[] parts = line.split("\t");
                if (parts.length < 3) {
                    throw new IOException("malformed row: " + line);
                }
                String fn = parts[0];
                long inputBits = parseHex64(parts[1]);
                long referenceBits = parseHex64(parts[2]);
                long libmBits = parts.length > 3 ? parseHex64(parts[3]) : referenceBits;

                double x = Double.longBitsToDouble(inputBits);
                double got = switch (fn) {
                    case "exp" -> StrictMath.exp(x);
                    case "log" -> StrictMath.log(x);
                    default -> throw new IOException("unknown function column: " + fn);
                };
                long gotBits = Double.doubleToRawLongBits(got);

                Tally t = tallies.computeIfAbsent(fn, k -> newTally());
                t.rows++;
                feed(t.inputDigest, inputBits);
                feed(t.outputDigest, gotBits);

                if (gotBits != referenceBits) {
                    t.mismatches++;
                    double ulp = ulpDistance(referenceBits, gotBits);
                    if (ulp > t.maxUlpError) {
                        t.maxUlpError = ulp;
                        t.worstInput = parts[1];
                    }
                    if (printed < PRINT_LIMIT) {
                        printed++;
                        System.out.printf(
                            "MISMATCH %-3s input=%s (%s)%n         numpy=%s%n         strictmath=%s"
                                + "  (%.0f ulp)%n",
                            fn, parts[1], Double.toString(x), parts[2], hex64(gotBits), ulp);
                    }
                }
                if (gotBits != libmBits) {
                    t.libmMismatches++;
                }
            }
        }

        boolean clean = true;
        System.out.println();
        System.out.println("artifact: " + path);
        System.out.println("jvm:      " + System.getProperty("java.vm.name") + " "
            + System.getProperty("java.version") + " on " + System.getProperty("os.arch"));
        for (Map.Entry<String, Tally> e : tallies.entrySet()) {
            Tally t = e.getValue();
            clean &= t.mismatches == 0;
            System.out.printf(
                "%-4s rows=%-9d StrictMath!=numpy=%-9d StrictMath!=libm=%-9d worst=%.0f ulp @ %s%n",
                e.getKey(), t.rows, t.mismatches, t.libmMismatches, t.maxUlpError, t.worstInput);
            System.out.printf("     digest inputs=%s%n", hex(t.inputDigest.digest()));
            System.out.printf("     digest strictmath=%s%n", hex(t.outputDigest.digest()));
        }
        System.out.println();
        System.out.println(clean
            ? "PARITY HOLDS: StrictMath reproduces every recorded value bit for bit."
            : "PARITY BROKEN: StrictMath and the Python reference disagree — see the rows above.");
        System.exit(clean ? 0 : 1);
    }

    private static Tally newTally() {
        try {
            return new Tally();
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    /** Big-endian, to match the Python side's `bits.astype('>u8').tobytes()`. */
    private static void feed(MessageDigest digest, long bits) {
        for (int shift = 56; shift >= 0; shift -= 8) {
            digest.update((byte) (bits >>> shift));
        }
    }

    private static long parseHex64(String token) {
        String body = token.startsWith("0x") || token.startsWith("0X") ? token.substring(2) : token;
        return Long.parseUnsignedLong(body, 16);
    }

    private static String hex64(long bits) {
        return String.format("0x%016x", bits);
    }

    private static String hex(byte[] bytes) {
        StringBuilder sb = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) {
            sb.append(String.format("%02x", b));
        }
        return sb.toString();
    }

    /** Ulp distance between two same-signed finite doubles — only used to describe a mismatch. */
    private static double ulpDistance(long a, long b) {
        return Math.abs((double) (a - b));
    }
}
