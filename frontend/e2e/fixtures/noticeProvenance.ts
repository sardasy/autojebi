/** Minimal fictional archives; stored entries make the fixture readable and deterministic. */
export function testZip(files: Record<string, Buffer | string>): Buffer {
  const local: Buffer[] = [], directory: Buffer[] = [];
  let offset = 0;
  for (const [name, value] of Object.entries(files)) {
    const bytes = Buffer.from(value), filename = Buffer.from(name);
    let crc = 0xffffffff;
    for (const byte of bytes) {
      crc ^= byte;
      for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
    }
    crc = (crc ^ 0xffffffff) >>> 0;
    const header = Buffer.alloc(30), central = Buffer.alloc(46);
    header.writeUInt32LE(0x04034b50); header.writeUInt16LE(20, 4); header.writeUInt16LE(0x800, 6);
    header.writeUInt32LE(crc, 14); header.writeUInt32LE(bytes.length, 18); header.writeUInt32LE(bytes.length, 22);
    header.writeUInt16LE(filename.length, 26);
    central.writeUInt32LE(0x02014b50); central.writeUInt16LE(20, 4); central.writeUInt16LE(20, 6);
    central.writeUInt16LE(0x800, 8); central.writeUInt32LE(crc, 16); central.writeUInt32LE(bytes.length, 20);
    central.writeUInt32LE(bytes.length, 24); central.writeUInt16LE(filename.length, 28); central.writeUInt32LE(offset, 42);
    local.push(header, filename, bytes); directory.push(central, filename);
    offset += header.length + filename.length + bytes.length;
  }
  const index = Buffer.concat(directory), end = Buffer.alloc(22), count = Object.keys(files).length;
  end.writeUInt32LE(0x06054b50); end.writeUInt16LE(count, 8); end.writeUInt16LE(count, 10);
  end.writeUInt32LE(index.length, 12); end.writeUInt32LE(offset, 16);
  return Buffer.concat([...local, index, end]);
}

export function fictionalHwpx(): Buffer {
  const lines = ["TEST ONLY - FICTIONAL NOTICE - DO NOT SUBMIT", "구축 예산 : 260,000,000원 (부가세 포함)",
    "납품 설치 기한 : 계약체결일로부터 120일 이내", "기술평가 점수 85점 이상을 협상 적격자로 선정한다.",
    "제안요청서 및 평가표를 확인한다.", "[서식 1] 제안서", "항목 1.", "...... (작성지침을 참고하여 자유롭게 기술)"];
  const xml = `<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">${lines.map(text => `<hp:p><hp:run><hp:t>${text}</hp:t></hp:run></hp:p>`).join("")}</hs:sec>`;
  return testZip({mimetype: "application/hwp+zip", "Contents/section0.xml": xml, "Preview/PrvText.txt": "TEST ONLY"});
}
