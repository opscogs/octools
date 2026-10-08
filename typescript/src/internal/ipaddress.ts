/**
 * IP address and network parsing with the rules the spec fixtures pin.
 *
 * The rules are those of Python's `ipaddress` module, which the Python
 * implementation uses: IPv4 is four dotted decimal octets with no leading
 * zeros; IPv6 is RFC 4291 text with at most one `::`, an optional IPv4
 * tail and an optional `%scope` suffix; a network is an address, `/` and a
 * prefix length (an IPv4 network also takes a dotted netmask or hostmask),
 * with host bits allowed.
 *
 * @module
 */

/** A parsed address: its version, its value and its IPv6 scope, if any. */
export interface IpAddress {
  readonly version: 4 | 6;
  readonly value: bigint;
  readonly scope: string | null;
}

const DECIMAL_RE = /^[0-9]+$/;
const HEXTET_RE = /^[0-9A-Fa-f]{1,4}$/;
const HEXTET_COUNT = 8;
const IPV4_BITS = 32;
const IPV6_BITS = 128;

/** Return the value of a dotted-quad IPv4 address, or null. */
function ipv4Value(text: string): bigint | null {
  const octets = text.split(".");
  if (octets.length !== 4) {
    return null;
  }
  let value = 0n;
  for (const octet of octets) {
    if (!DECIMAL_RE.test(octet) || octet.length > 3) {
      return null;
    }
    if (octet !== "0" && octet.startsWith("0")) {
      return null;
    }
    const number = Number(octet);
    if (number > 255) {
      return null;
    }
    value = (value << 8n) | BigInt(number);
  }
  return value;
}

/** Return the value of IPv6 text without a scope, or null. */
function ipv6Value(text: string): bigint | null {
  const parts = text.split(":");
  if (parts.length < 3) {
    return null;
  }
  const last = text.slice(text.lastIndexOf(":") + 1);
  if (last.includes(".")) {
    const tail = ipv4Value(last);
    if (tail === null) {
      return null;
    }
    parts.pop();
    parts.push((tail >> 16n).toString(16), (tail & 0xffffn).toString(16));
  }
  if (parts.length > HEXTET_COUNT + 1) {
    return null;
  }
  let skip: number | null = null;
  for (let index = 1; index < parts.length - 1; index += 1) {
    if (parts[index] === "") {
      if (skip !== null) {
        return null;
      }
      skip = index;
    }
  }
  let high: number;
  let low: number;
  let skipped: number;
  if (skip !== null) {
    high = skip;
    low = parts.length - skip - 1;
    if (parts[0] === "") {
      high -= 1;
      if (high !== 0) {
        return null;
      }
    }
    if (parts[parts.length - 1] === "") {
      low -= 1;
      if (low !== 0) {
        return null;
      }
    }
    skipped = HEXTET_COUNT - (high + low);
    if (skipped < 1) {
      return null;
    }
  } else {
    if (parts.length !== HEXTET_COUNT) {
      return null;
    }
    high = parts.length;
    low = 0;
    skipped = 0;
  }
  const head = parts.slice(0, high);
  const tail = parts.slice(parts.length - low);
  if (![...head, ...tail].every((hextet) => HEXTET_RE.test(hextet))) {
    return null;
  }
  let value = 0n;
  for (const hextet of [
    ...head,
    ...Array<string>(skipped).fill("0"),
    ...tail,
  ]) {
    value = (value << 16n) | BigInt(Number.parseInt(hextet, 16));
  }
  return value;
}

/** Parse an IPv4 address, or return null. */
function parseIpv4(text: string): IpAddress | null {
  const value = text.includes("/") ? null : ipv4Value(text);
  return value === null ? null : { version: 4, value, scope: null };
}

/** Parse an IPv6 address with an optional `%scope`, or return null. */
function parseIpv6(text: string): IpAddress | null {
  if (text.includes("/")) {
    return null;
  }
  const mark = text.indexOf("%");
  let address = text;
  let scope: string | null = null;
  if (mark >= 0) {
    address = text.slice(0, mark);
    scope = text.slice(mark + 1);
    if (scope === "" || scope.includes("%")) {
      return null;
    }
  }
  if (address === "") {
    return null;
  }
  const value = ipv6Value(address);
  return value === null ? null : { version: 6, value, scope };
}

/** Parse an IPv4 or IPv6 address, or return null. */
export function parseIpAddress(text: string): IpAddress | null {
  return parseIpv4(text) ?? parseIpv6(text);
}

/** Return the prefix length of a contiguous-ones netmask value, or null. */
function prefixFromMask(mask: bigint, bits: number): number | null {
  let zeros = 0;
  while (zeros < bits && ((mask >> BigInt(zeros)) & 1n) === 0n) {
    zeros += 1;
  }
  const prefix = bits - zeros;
  const ones = (1n << BigInt(prefix)) - 1n;
  return mask >> BigInt(zeros) === ones ? prefix : null;
}

/** True when `text` is a decimal prefix length no longer than `bits`. */
function isPrefixLength(text: string, bits: number): boolean {
  return DECIMAL_RE.test(text) && Number(text) <= bits;
}

/** True when `text` is a dotted IPv4 netmask or hostmask. */
function isIpv4Mask(text: string): boolean {
  const mask = ipv4Value(text);
  if (mask === null) {
    return false;
  }
  const all = (1n << BigInt(IPV4_BITS)) - 1n;
  return (
    prefixFromMask(mask, IPV4_BITS) !== null ||
    prefixFromMask(mask ^ all, IPV4_BITS) !== null
  );
}

/** True when `text` is an IPv4 or IPv6 network; host bits may be set. */
export function isIpNetwork(text: string): boolean {
  const parts = text.split("/");
  if (parts.length > 2) {
    return false;
  }
  const [address = "", mask] = parts;
  if (parseIpv4(address) !== null) {
    return (
      mask === undefined || isPrefixLength(mask, IPV4_BITS) || isIpv4Mask(mask)
    );
  }
  if (parseIpv6(address) !== null) {
    return mask === undefined || isPrefixLength(mask, IPV6_BITS);
  }
  return false;
}

/**
 * True when `first` sorts at or before `last`. Two IPv6 addresses with the
 * same value but different scopes are unordered, so neither is at or
 * before the other.
 */
export function isAtOrBefore(first: IpAddress, last: IpAddress): boolean {
  return (
    first.value < last.value ||
    (first.value === last.value && first.scope === last.scope)
  );
}
